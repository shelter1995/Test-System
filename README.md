# Test-System

AI 销售话术陪练与 RAG 知识库系统。项目由两个本地服务组成：

- `rag-anything-api/`：RAG-Anything 知识库服务，默认端口 `8003`
- `ai-tutor-system/`：AI 话术陪练系统和前端界面，默认端口 `8002`

## 主要功能

- 知识库上传、解析、检索与删除
- 基于知识库的销售话术陪练
- 多场景客户对练，包括价格敏感、技术挑剔、决策谨慎、竞品对比
- 每轮对话评分和最终训练报告
- 一键启动两个服务并打开浏览器页面

## 快速启动

1. 配置环境变量：

   - `rag-anything-api/.env`
   - `ai-tutor-system/.env`

2. 在项目根目录运行：

   ```bat
   start_services.bat
   ```

3. 浏览器访问：

   - 陪练系统：http://localhost:8002
   - RAG API 文档：http://localhost:8003/docs
   - 陪练 API 文档：http://localhost:8002/docs

## 依赖说明

项目需要本地 Python 虚拟环境和外部模型服务：

- MiniMax API：用于陪练对话和评分
- 硅基流动 API：用于 embedding、rerank 等模型调用
- MinerU：用于 PDF/Office 文档解析，文本导入不依赖它
- 传统 RAG：默认知识库引擎，用于常见文本、PDF、Word、Excel 文件的快速导入和检索。
- RAG-Anything：高级引擎，用于复杂 PDF、多模态、音视频和图谱增强场景。

依赖安装和环境配置见 [SETUP.md](SETUP.md)。

## 知识库引擎

### 传统 RAG（默认）

新建知识库默认使用「传统 RAG」引擎。它基于 SQLite 向量存储和文本分块，无需 GPU 或额外依赖即可完成以下格式的导入和检索：

- 文本文件：`.txt`, `.md`, `.csv`
- 文档文件：`.pdf`, `.docx`, `.xlsx`

传统 RAG 在知识库列表中显示蓝色「传统 RAG」标签。

### RAG-Anything（高级引擎）

RAG-Anything 提供知识图谱、多模态处理和音视频解析能力，适合需要深层语义理解的场景：

- 复杂 PDF（含表格、图片、公式）
- 图片文件：`.jpg`, `.png`, `.bmp`
- 视频文件：`.mp4`, `.avi`, `.mkv`
- 音频文件：`.mp3`, `.wav`, `.flac`

切换方式：创建知识库时通过 API 指定 `engine: "raganything"`，或在 Web 界面的知识库详情中修改引擎类型。已导入文档的引擎类型在知识库列表和文档列表中均有标签显示。

## 模型配置

### Web 界面配置

启动服务后，打开 http://localhost:8002 切换到「模型设置」页面，可在线修改以下三组模型的供应商、接口地址、模型名和 API Key：

| 模型组 | 默认供应商 | 用途 |
|--------|-----------|------|
| 推理模型 | MiniMax | 陪练对话、评分、内容生成 |
| 嵌入模型 | 硅基流动 (BAAI/bge-m3) | 文本转向量 |
| 重排模型 | 硅基流动 (BAAI/bge-reranker-v2-m3) | 检索结果重排序 |

配置修改后实时生效，无需重启服务。

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
python -m pytest ai-tutor-system\tests -q
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

生成可分发的 Windows 便携包（包含虚拟环境和所有依赖）：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

产出：`dist-portable/Test-System-Portable.zip`

便携包解压后运行 `start_services.bat` 即可使用。用户仍需在 `.env` 中配置 MiniMax 和硅基流动的 API Key。

## 文档

- [SETUP.md](SETUP.md)：环境安装与启动说明
- [CHANGELOG.md](CHANGELOG.md)：项目变更记录
- [使用说明.md](使用说明.md)：业务使用流程
- [部署说明.md](部署说明.md)：部署相关说明
