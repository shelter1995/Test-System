# Test-System 便携包 MinerU 按需安装设计

## 目标

为不熟悉电脑操作的 Windows 用户提供一个体积可控、解压后可双击启动的 Test-System 便携包。

便携包包含固定版本的 Python、项目源码和基础运行依赖，但不包含 MinerU 模型。系统首次启动时检查 MinerU 状态，由用户确认后自动安装；模型在首次实际解析复杂文档时下载。

成功标准：

- 用户无需安装系统 Python，也无需手动输入 `pip` 命令。
- 未安装 MinerU 时，8002 和 8003 服务仍能启动。
- 安装 MinerU 后可解析扫描 PDF、图片和复杂文档。
- 模型文件不进入发布压缩包。
- 解压目录移动后仍能运行，不依赖打包机绝对路径。
- 新安装环境不自动创建没有实际索引数据的“商务彩铃”知识库。

## 发布运行时

基础包固定使用经过虚拟机验证的 CPython `3.13.10`。

包内目录结构：

```text
Test-System-Portable/
├── runtime/
│   ├── python/                 # CPython 3.13.10
│   ├── base-site-packages/     # 项目基础依赖
│   ├── optional-site-packages/ # 用户确认后安装 MinerU
│   ├── models/mineru/          # MinerU 模型缓存，不进入 zip
│   ├── tools/ffmpeg/
│   └── logs/
├── rag-anything-api/
├── ai-tutor-system/
├── install_mineru.bat
└── start_services.bat
```

不再复制开发环境 `.venv`。构建过程使用干净的发布目录安装基础依赖，避免 Windows console-script `.exe` 内嵌开发机 Python 绝对路径。

所有 Python 命令都由包内解释器执行。MinerU 不通过复制的 `mineru.exe` 调用，而使用包内 Python 模块入口，或在目标机器安装后生成的本地入口。

## 依赖锁定

项目维护两组依赖：

- 基础依赖：FastAPI、Uvicorn、RAG、Office 轻量解析、Whisper 等启动所需依赖。
- 可选依赖：MinerU 及其 Torch、Torchvision、ONNX Runtime 等完整依赖树。

发布时使用锁文件或带哈希的约束文件，不再使用无上限的 `>=` 作为实际安装依据。MinerU 的发布版本从已通过虚拟机验收的环境导出并固定；升级 MinerU 必须重新执行完整验收矩阵，不能在用户机器上自动安装当日最新版。

安装器应使用类似以下语义：

```text
runtime\python\python.exe -m pip install
  --target runtime\optional-site-packages
  --requirement packaging\mineru-lock.txt
```

安装目录位于项目内部，不修改系统 Python，不要求管理员权限。

## 启动检查

`start_services.bat` 先调用一个 Python 运行时检查器。检查器输出结构化状态，至少包含：

- `python_ready`
- `base_dependencies_ready`
- `mineru_package_installed`
- `mineru_cli_runnable`
- `mineru_models_ready`
- `ffmpeg_ready`
- `libreoffice_ready`

不能只以文件是否存在判断 MinerU 可用。必须由包内 Python 实际加载 MinerU 模块并执行轻量探测。

启动决策：

1. Python 或基础依赖损坏：停止启动，显示中文错误和日志路径。
2. MinerU 未安装：询问用户是否安装。
3. 用户选择安装：打开独立安装窗口，显示阶段和日志；安装成功后重新检查。
4. 用户选择暂不安装：继续启动两个服务，并把 MinerU 标记为不可用。
5. MinerU 已安装但模型未下载：正常启动，等待首次需要时下载。

## 用户交互

首次启动检测到 MinerU 未安装时显示：

```text
检测到“复杂文档智能解析组件 MinerU”尚未安装。

安装后可处理扫描版 PDF、图片和复杂排版文档。
安装需要联网，并会占用较多磁盘空间。

[Y] 立即安装
[N] 暂不安装，先进入系统
```

安装过程至少显示：

- 正在检查网络；
- 正在下载依赖；
- 正在安装；
- 正在验证 MinerU；
- 安装完成，或失败原因与日志位置。

用户取消或安装失败时不得阻止系统基础功能启动。

前端依赖状态页面应显示“未安装、已安装未下载模型、可用、安装失败”四种状态，并提供重新安装入口。

## 模型按需下载

模型缓存固定到：

```text
runtime/models/mineru/
```

启动脚本和后端统一设置 MinerU、Hugging Face、ModelScope 所需缓存环境变量，防止模型散落到用户目录。

首次上传需要 MinerU 的文件时：

1. 检查 MinerU 包是否可用。
2. 未安装时返回明确的“需要安装 MinerU”状态。
3. 已安装但模型缺失时启动模型下载任务。
4. 前端通过现有 SSE 进度机制显示下载阶段、进度和失败信息。
5. 下载中断后保留可复用缓存，允许重新尝试。
6. 下载完成后执行解析，不要求用户重新上传文件。

模型下载失败不得破坏已安装的 Python 依赖。

## 文档解析降级

MinerU 不是系统启动的硬依赖。

未安装或不可用时：

- `.txt`、`.md`、`.csv` 正常处理。
- `.docx`、`.xlsx`、`.pptx` 使用现有轻量解析器。
- 文本型 PDF 优先使用 `pypdf`。
- 扫描 PDF、图片 OCR 和需要复杂版面分析的文件返回可操作提示。
- 音视频继续按 ffmpeg 和 Whisper 的独立状态判断。
- 旧 `.doc`、`.xls`、`.ppt` 仍取决于 LibreOffice。

后端错误信息必须说明缺少的具体组件，不使用笼统的“文档解析失败”。

## 知识库初始化

便携包继续排除开发机的 `rag-anything-api/storage`、会话和用户生成数据。

首次启动没有注册表时：

- 创建空注册表；
- 不自动注册“商务彩铃”；
- 不自动创建任何历史 `raganything` 知识库；
- 用户新建的知识库统一使用 `traditional` 引擎。

如果未来需要提供演示知识库，必须同时打包完整注册表、源文件和对应索引，并经过存储审计，不能只提供一个库名称。

## 日志与恢复

安装和模型下载日志存放在：

```text
runtime/logs/mineru-install.log
runtime/logs/mineru-model-download.log
runtime/logs/runtime-check.json
```

安装器使用临时目录完成下载和安装，成功后再更新安装状态。失败时清理未完成的临时目录，但保留日志。

提供以下恢复操作：

- 重新检查；
- 重新安装 MinerU；
- 清理并重新下载模型；
- 仅启动基础功能。

任何恢复操作都不得删除知识库、会话和模型设置。

## 测试与发布验收

自动化测试覆盖：

- 包内不包含开发机绝对路径。
- console-script 启动器不从开发 `.venv` 复制。
- 未安装 MinerU 时服务可启动。
- 用户拒绝安装后基础功能可用。
- 安装失败时返回中文错误和日志路径。
- 空存储首次启动不会创建“商务彩铃”。
- 模型缓存环境变量指向包内目录。
- MinerU 探测实际执行模块，不只检查文件存在。

每个发布包必须在全新 Windows 虚拟机验收：

1. 虚拟机没有系统 Python、MinerU、模型缓存和项目源码。
2. 将 zip 解压到包含中文和空格的路径。
3. 双击启动并选择暂不安装，确认两个服务和基础解析可用。
4. 重新启动并选择安装，确认 MinerU 自动安装成功。
5. 上传一份扫描 PDF，确认模型下载、进度显示和最终解析成功。
6. 上传 Word、PPT、Excel 和文本型 PDF，确认轻量解析路径正常。
7. 移动整个解压目录后再次启动，确认无绝对路径依赖。
8. 断网重启，确认已安装依赖和已下载模型可复用。

只有完整通过上述验收，才能将压缩包标记为“解压后双击即可使用”。
