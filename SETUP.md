# Test-System 部署与使用说明

> 面向自动化 Agent 和人类操作员的完整部署文档。按顺序执行即可。

---

## 1. 系统要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | **3.12 ~ 3.13** | RAG-Anything 对 3.14 兼容性不佳，3.12/3.13 最稳定 |
| Git | 2.30+ | 克隆仓库 |
| pip | 24.0+ | Python 包管理 |
| 磁盘空间 | ≥ 10 GB | MinerU 模型文件约 3-5 GB，RAG 存储需预留空间 |
| 内存 | ≥ 8 GB | MinerU 解析较大 PDF 时内存占用高 |

### 可选（高级功能）

| 组件 | 需要时安装 | 用途 |
|------|----------|------|
| MinerU | `pip install -U "mineru[core]"` | PDF/Office 文档解析 |

---

## 2. 获取项目

```bash
git clone <Test-System-仓库地址>
cd Test-System
```

---

## 3. 创建 Python 虚拟环境（推荐）

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

---

## 4. 安装依赖

```bash
# RAG 服务依赖（raganything 引擎已内置于项目中）
pip install -r rag-anything-api/requirements.txt

# MinerU 文档解析（可选，跳过则仅支持文本导入）
pip install -U "mineru[core]"

# Tutor 服务依赖
pip install -r ai-tutor-system/requirements_tutor.txt
```

> RAG-Anything 引擎源码已包含在 `rag-anything-api/raganything/` 目录中，无需额外安装。

---

## 5. 配置环境变量

### 5.1 复制模板

```bash
cp rag-anything-api/.env.example rag-anything-api/.env
cp ai-tutor-system/.env.example ai-tutor-system/.env
```

### 5.2 填写密钥 — `rag-anything-api/.env`

```ini
# 必填
MINIMAX_API_KEY=你的MiniMax_API_Key
SILICONFLOW_API_KEY=你的硅基流动_API_Key

# 可选：MiniMax Coding Plan VLM（图片理解）
ENABLE_VLM=true              # 需要 Coding Plan 套餐
VLM_API_KEY=                 # 留空自动复用 MINIMAX_API_KEY
VLM_BASE_URL=https://api.minimaxi.com

# 可选：硅基流动 Rerank（检索重排序）
ENABLE_RERANK=true
RERANK_API_KEY=              # 留空自动复用 SILICONFLOW_API_KEY

# 查询模式：hybrid（推荐 / 向量+图谱融合）
DEFAULT_QUERY_MODE=hybrid

# 传统 RAG 引擎（默认）
DEFAULT_RAG_ENGINE=traditional
TRADITIONAL_CHUNK_SIZE=1200
TRADITIONAL_CHUNK_OVERLAP=120
```

### 5.3 填写密钥 — `ai-tutor-system/.env`

```ini
MINIMAX_API_KEY=你的MiniMax_API_Key
MINIMAX_MODEL=MiniMax-M2.7
RAG_SERVICE_URL=http://localhost:8003
```

### 5.4 密钥获取地址

| 服务 | 注册地址 |
|------|---------|
| MiniMax API | https://platform.minimaxi.com |
| 硅基流动 API | https://siliconflow.cn |

---

## 6. 知识库初始化（首次使用）

启动 RAG 服务后，上传文档到知识库：

```bash
# 方式1：上传文件（HTML 表单）
curl -X POST http://localhost:8003/ingest/upload \
  -F "database=我的知识库" \
  -F "files=@/path/to/document.pdf"

# 方式2：上传文本
curl -X POST http://localhost:8003/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text":"你的文本内容","database":"我的知识库"}'

# 方式3：导入目录（批量）
curl -X POST http://localhost:8003/ingest/path \
  -H "Content-Type: application/json" \
  -d '{"path":"/path/to/documents","database":"我的知识库","recursive":true}'
```

支持格式：`.pdf .doc .docx .ppt .pptx .xls .xlsx .txt .md .jpg .png .bmp .mp4 .mp3` 等。

---

## 7. 启动服务

### 终端1：RAG 服务（端口 8003）

```bash
cd rag-anything-api
python start.py
```

启动成功标志：
```
[OK] 依赖检查通过
正在启动 RAG-Anything API 服务...
INFO:     Uvicorn running on http://0.0.0.0:8003
```

### 终端2：Tutor 服务（端口 8002）

```bash
cd ai-tutor-system
python tutor_backend.py
```

启动成功标志：
```
[OK] MiniMax AI 已配置
[OK] SSE 流式输出已启用
INFO:     Uvicorn running on http://0.0.0.0:8002
```

### 浏览器

打开 `http://localhost:8002`，即可使用完整工作台（知识库 + 内容生成 + AI 陪练）。

---

## 7.1 桌面快捷方式

在桌面创建快捷方式，双击即可一键启动所有服务：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\create_shortcut.ps1
```

快捷方式指向 `start_services.bat`，会自动检测服务是否已在运行，启动后打开浏览器访问 http://localhost:8002。

---

## 7.2 模型配置

### Web 界面配置

启动服务后，打开 http://localhost:8002 切换到「模型设置」页面，可在线修改以下三组模型：

| 模型组 | 配置项 | 说明 |
|--------|--------|------|
| 推理模型 | 供应商、接口地址、模型名、API Key | 陪练对话、评分、内容生成 |
| 嵌入模型 | 供应商、接口地址、模型名、API Key | 文本转向量 |
| 重排模型 | 供应商、接口地址、模型名、API Key | 检索结果重排序 |

配置修改后实时生效，无需重启服务。

### 自定义 OpenAI-compatible 端点

支持任何兼容 OpenAI 协议的 API 端点。在模型设置页面中：

1. 将「供应商」填写为 `openai`
2. 「接口地址」填写目标 API 地址（如 `http://localhost:11434/v1`）
3. 「API Key」填写对应的密钥

适用于本地 Ollama、vLLM、其他第三方兼容服务等场景。

### 环境变量直接配置

也可以直接编辑 `.env` 文件配置模型参数：

```ini
# rag-anything-api/.env
MINIMAX_API_KEY=sk-your-key
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL_M27=MiniMax-M2.7

SILICONFLOW_API_KEY=sk-your-key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn
SILICONFLOW_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024

# 可选：Rerank
ENABLE_RERANK=true
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

---

## 7.3 知识库引擎

### 传统 RAG（默认）

新建知识库默认使用「传统 RAG」引擎，基于 SQLite 向量存储和文本分块，无需 GPU 或额外依赖。支持格式：`.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.xlsx`。

传统 RAG 在知识库列表和文档列表中显示蓝色「传统 RAG」标签。

### 切换到 RAG-Anything

RAG-Anything 提供知识图谱、多模态处理和音视频解析能力。切换方式：

- **新建知识库时**：通过 API `POST /db/register` 传入 `engine: "raganything"`
- **已有知识库**：通过 API `PUT /db/{db_id}` 修改引擎类型

RAG-Anything 额外支持：`.jpg`, `.png`, `.bmp`, `.mp4`, `.avi`, `.mkv`, `.mp3`, `.wav`, `.flac` 等格式。使用音视频功能需配置 ffmpeg 和 whisper。

---

## 8. 验证部署

```bash
# RAG 服务健康检查
curl -s http://localhost:8003/health
# 期望：{"status":"healthy","engine":"ready"}

# RAG 服务完整状态
curl -s http://localhost:8003/status | python -m json.tool
# 检查：engine=ready, vlm.enabled=true, rerank.enabled=true, query.default_mode=hybrid

# Tutor 服务健康检查
curl -s http://localhost:8002/
# 期望返回服务信息

# 测试搜索
curl -s -X POST http://localhost:8003/search \
  -H "Content-Type: application/json" \
  -d '{"query":"测试","database":"你的知识库名","n_results":2}'
```

---

## 9. 目录结构速查

```
Test-System/
├── rag-anything-api/          # RAG 服务（端口 8003）
│   ├── .env                   # 需配置 API 密钥
│   ├── .env.example           # 配置模板
│   ├── start.py               # 启动脚本（自动依赖检查）
│   ├── app.py                 # FastAPI 路由
│   ├── config.py              # 配置项
│   ├── raganything_service.py # RAG-Anything 封装（VLM + Rerank）
│   └── storage/               # 知识库持久化（gitignored）
│
├── ai-tutor-system/           # Tutor 服务（端口 8002）
│   ├── .env                   # 需配置 API 密钥
│   ├── .env.example           # 配置模板
│   ├── tutor_backend.py       # 启动入口
│   ├── tutor_config.py        # 会话/场景/评估维度配置
│   ├── tutor_services.py      # RAG/AI/会话/报告 服务层
│   ├── tutor_streaming.py     # SSE 流式管线
│   └── static/                # 前端 SPA
│
├── README.md                  # 项目入口说明
├── CHANGELOG.md               # 项目变更记录
└── SETUP.md                   # 本文件
```

---

## 10. 使用指南

### 知识库管理

启动后浏览器打开 `http://localhost:8002`，左侧导航切换到「知识库」。

1. 点击「新建知识库」，输入名称（如"产品文档"）
2. 拖拽或选择文件上传（支持 PDF、Word、图片等）
3. 等待解析完成（进度条实时显示）
4. 搜索框输入关键词测试检索

### AI 话术陪练

切换到「陪练系统」页面：

1. 选择陪练场景（如"商务视频彩铃销售"）
2. 点击「开始陪练」进入对话
3. 输入回复，AI 会逐字流式输出
4. 每轮结束后自动评分（五维度：准确性/流畅度/说服力/专业性/亲和力）
5. 右侧面板查看累计评分趋势
6. 结束会话后生成详细报告

### 内容生成

切换到「内容生成」页面：

- **解决方案**：输入客户背景、痛点、决策偏好 → 生成 SCQA 结构化方案
- **培训材料**：输入主题、对象、时长 → 生成讲义 + 测试题 + README

生成产物保存在 `generation_output/` 目录。

---

## 10.1 便携打包

生成可分发的 Windows 便携包（包含虚拟环境和所有依赖）：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

产出：`dist-portable/Test-System-Portable.zip`

### 便携包使用

1. 解压 `Test-System-Portable.zip`
2. 编辑 `rag-anything-api/.env` 和 `ai-tutor-system/.env`，填入 API Key
3. 运行 `start_services.bat`
4. 浏览器自动打开 http://localhost:8002

便携包包含完整的 Python 虚拟环境，无需单独安装 Python 或依赖。

---

## 11. 常见问题

### MinerU 安装失败

```bash
# 跳过 MinerU，知识库仍可通过文本导入正常工作
# 如需完整 PDF 解析能力，参考：https://github.com/opendatalab/MinerU
```

### 依赖缺失

```bash
# 确保所有依赖正确安装
pip install -r rag-anything-api/requirements.txt
pip install -r ai-tutor-system/requirements_tutor.txt
```

### 端口被占用

```bash
# 修改 rag-anything-api/.env
RAG_SERVICE_PORT=8004

# 修改 ai-tutor-system/.env
RAG_SERVICE_URL=http://localhost:8004
```
