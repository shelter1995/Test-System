# Test-System

AI 销售话术陪练与 RAG 知识库系统。项目由两个本地服务组成：

- `rag-anything-api/`：知识库服务（统一传统 RAG，内部兼容历史 RAG-Anything 数据），默认端口 `8003`
- `ai-tutor-system/`：AI 话术陪练系统和前端界面，默认端口 `8002`

## 主要功能

- 知识库上传、解析、检索与删除
- 知识库问答，支持切换知识库、多轮提问和来源依据展示
- 基于知识库的销售话术陪练
- 多场景客户对练，包括价格敏感、技术挑剔、决策谨慎、竞品对比
- 每轮对话评分和最终训练报告
- 一键启动两个服务并打开浏览器页面

## 快速启动

1. 创建并激活虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

2. 安装运行依赖：

   ```powershell
   python -m pip install --upgrade pip
   pip install -r rag-anything-api\requirements.txt
   pip install -r ai-tutor-system\requirements_tutor.txt
   ```

   如需运行测试，可改装开发依赖：

   ```powershell
   pip install -r requirements-dev.txt
   ```

3. 复制并配置环境变量：

   - `rag-anything-api/.env`
   - `ai-tutor-system/.env`

   可从对应目录的 `.env.example` 复制生成。

4. 在项目根目录运行：

   ```bat
   start_services.bat
   ```

5. 浏览器访问：

   - 陪练系统：http://localhost:8002
   - RAG API 文档：http://localhost:8003/docs
   - 陪练 API 文档：http://localhost:8002/docs

## 依赖说明

项目需要本地 Python 虚拟环境和外部模型服务：

- 统一 LLM API：用于知识库问答、陪练对话、评分和内容生成，可在前端「模型设置」页面配置
- 硅基流动 API：用于 embedding、rerank 等模型调用
- MinerU：用于扫描 PDF、复杂 PDF 和图片 OCR 解析
- LibreOffice：用于 `.doc/.xls/.ppt` 老 Office 格式转为现代格式后解析
- ffmpeg：用于视频抽取音轨
- openai-whisper：用于音频和视频语音转写

依赖安装和环境配置见 [SETUP.md](SETUP.md)。

## 知识库能力

用户可见的知识库能力统一为传统 RAG（向量检索 + 重排），不再提供 RAG-Anything 引擎切换入口。

支持格式：

- 文档：`.pdf`、`.doc`、`.docx`、`.xls`、`.xlsx`、`.ppt`、`.pptx`、`.txt`、`.md`、`.csv`
- 图片：`.png`、`.jpg`、`.jpeg`、`.bmp`、`.tiff`、`.webp`
- 音频：`.mp3`、`.wav`、`.flac`、`.aac`、`.ogg`、`.m4a`、`.wma`
- 视频：`.mp4`、`.avi`、`.mkv`、`.mov`、`.webm`、`.wmv`、`.m4v`

当前传统 RAG 的视频解析基于“抽取音轨 -> Whisper 转写 -> 文本入库”。无音频视频暂不支持通过抽取关键帧、图片 OCR 或 VLM 理解画面内容；该能力作为后续功能规划。

传统 RAG 默认使用硅基流动嵌入和重排模型，并内置批量嵌入与 429 限流重试。长文本批量上传时，可通过 `EMBEDDING_BATCH_SIZE`、`EMBEDDING_BATCH_INTERVAL`、`EMBEDDING_RETRY_ATTEMPTS` 和 `EMBEDDING_RETRY_BASE_DELAY` 调整吞吐与稳定性。

系统内部仍兼容历史 RAG-Anything 数据目录和索引结构，用于旧数据平滑迁移与读取，但该兼容能力不作为用户操作选项暴露。

## 模型配置

### Web 界面配置

启动服务后，打开 http://localhost:8002 切换到「模型设置」页面，可在线修改以下三组模型的供应商、接口地址、模型名和 API Key：

| 模型组 | 默认供应商 | 用途 |
|--------|-----------|------|
| 推理模型 | MiniMax（可改为 DeepSeek 等 OpenAI-compatible 服务） | 知识库问答、陪练对话、评分、内容生成 |
| 嵌入模型 | 硅基流动 (BAAI/bge-m3) | 文本转向量 |
| 重排模型 | 硅基流动 (BAAI/bge-reranker-v2-m3) | 检索结果重排序 |

配置修改后实时生效，无需重启服务。

保存与测试逻辑：

- 点击「保存」会持久化当前配置，刷新页面后可恢复。
- 点击「测试连接」优先使用当前表单里新填写的地址、模型名和密钥。
- 如果当前表单没有填写新密钥，测试会使用已保存密钥。
- 保存成功后，知识库上传、重试、问答、内容生成和陪练会读取最新运行时配置。

### 自定义 OpenAI-compatible 端点

支持任何 OpenAI-compatible 的 API 端点。在模型设置页面中将「供应商」填写为 `openai`，「接口地址」填写目标 API 地址，「API Key」填写对应的密钥即可。例如：

- 本地 Ollama：接口地址 `http://localhost:11434/v1`
- 其他兼容 OpenAI 协议的第三方服务

### 环境变量配置

也可以直接编辑 `.env` 文件配置模型参数，详见 [SETUP.md](SETUP.md) 的环境变量说明。

## 项目结构

```text
Test-System/
├── README.md
├── CHANGELOG.md
├── SETUP.md
├── requirements-dev.txt
├── start_services.bat
├── ai-tutor-system/
│   ├── tutor_backend.py
│   ├── tutor_services.py
│   ├── static/
│   └── tests/
└── rag-anything-api/
    ├── app.py
    ├── raganything_service.py
    ├── database_registry.py
    └── tests/
```

## 常用命令

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests -q
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests -q
```

编译检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api
```

## 桌面快捷方式

在桌面创建快捷方式，双击即可一键启动所有服务：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\create_shortcut.ps1
```

快捷方式会自动检测服务是否已在运行，启动后打开浏览器访问 http://localhost:8002。

## 便携打包

生成可分发的 Windows 便携包：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

产出：`dist-portable/Test-System-Portable.zip`

便携包包含独立 CPython 3.13.10 和基础依赖，不复制开发环境 `.venv`，目标电脑无需安装 Python、pip 或 uv。解压后双击 `start_services.bat` 即可启动。

为控制压缩包大小，MinerU 及模型不预先打包。首次启动会询问是否联网安装 MinerU；用户可以暂不安装并使用基础文档解析。首次解析扫描 PDF 或图片时，MinerU 模型会下载到包内 `runtime/models/mineru/`。

用户仍需在模型设置中配置统一 LLM、嵌入和重排模型的 API Key。详细说明见 [packaging/README.md](packaging/README.md)。

## Windows 桌面安装包

面向最终用户的 Windows 原生安装体验：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

产出：`dist-installer\Test-System-Setup-<版本>-x64.exe`

安装包特点：
- 双击安装，可选择程序和数据路径
- 使用 WebView2 嵌入浏览器，无需单独打开浏览器
- 关闭窗口会自动停止后端服务
- 升级安装保留数据目录
- 卸载默认保留数据（可选删除）
- 可选安装 MinerU 增强解析组件

面向开发者的详细发布流程见 [docs/releasing-windows.md](docs/releasing-windows.md)。普通用户使用便携包即可（见上文便携打包章节）。

## 文档

- [SETUP.md](SETUP.md)：环境安装与启动说明
- [CHANGELOG.md](CHANGELOG.md)：项目变更记录
- [使用说明.md](使用说明.md)：业务使用流程
- [部署说明.md](部署说明.md)：部署相关说明
