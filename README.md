# Test-System — 企业 AI 工作台

> 集成知识库管理、AI 内容生成、话术陪练的 Web 应用。基于商务视频彩铃场景构建，支持任意知识库。

## 核心功能

| 模块 | 说明 |
|------|------|
| **知识库** | 上传文档（PDF/Word/图片/音视频），自动解析入库，支持向量+图谱混合检索 |
| **内容生成** | 基于知识库生成解决方案、培训讲义、测试题 |
| **AI 话术陪练** | 多场景角色扮演，SSE 流式对话，实时五维评分 |
| **历史产物** | 查看并下载生成的 Markdown 文件 |

## 系统架构

```
浏览器 → http://localhost:8002（统一工作台 SPA）
    ├── RAG 服务 (localhost:8003) — FastAPI + RAG-Anything + LightRAG
    │   ├── /ingest/upload        文件上传（SSE 进度）
    │   ├── /search, /query       混合检索（向量+图谱）
    │   ├── /context              轻量上下文提取
    │   └── /db/list, /db/stats   知识库管理
    │
    └── Tutor 服务 (localhost:8002) — FastAPI
        ├── /chat/stream          SSE 流式陪练
        ├── /session/*            会话管理
        ├── /scenarios            场景管理
        ├── /generation/jobs/*    内容生成
        └── /history              历史记录
```

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. 安装依赖
pip install -r rag-anything-api/requirements.txt
pip install -r ai-tutor-system/requirements_tutor.txt

# 3. 配置密钥
cp rag-anything-api/.env.example rag-anything-api/.env
cp ai-tutor-system/.env.example ai-tutor-system/.env
# 编辑两个 .env 文件，填入 MiniMax API Key 和硅基流动 API Key

# 4. 启动服务（两个终端）
cd rag-anything-api && python start.py        # 端口 8003
cd ai-tutor-system && python tutor_backend.py # 端口 8002

# 5. 打开浏览器访问 http://localhost:8002
```

> 详细部署步骤见 [SETUP.md](SETUP.md)。

## 目录结构

```
Test-System/
├── rag-anything-api/          # RAG 服务（端口 8003）
│   ├── start.py               # 启动脚本（自动依赖检查）
│   ├── app.py                 # FastAPI 路由
│   ├── raganything_service.py # RAG-Anything 封装
│   └── .env.example           # 配置模板
│
├── ai-tutor-system/           # Tutor 服务 + 前端（端口 8002）
│   ├── tutor_backend.py       # FastAPI 启动入口
│   ├── tutor_services.py      # 业务逻辑层
│   ├── tutor_streaming.py     # SSE 流式管线
│   ├── generation_api.py      # 内容生成 API
│   ├── static/index.html      # 统一工作台 SPA
│   └── .env.example           # 配置模板
│
├── solution-generator-skill/  # 解决方案生成技能定义
├── peixun-skill/              # 培训材料生成技能定义
├── generation_output/         # 生成产物输出目录（gitignored）
├── SETUP.md                   # 详细部署指南
├── 使用说明.md                 # 功能使用指南
├── 部署说明.md                 # 部署与运维参考
└── CLAUDE.md                  # 项目架构与开发文档（供 AI 参考）
```

## 文档索引

- **[SETUP.md](SETUP.md)** — 首次部署完整步骤（环境、依赖、配置、验证）
- **[使用说明.md](使用说明.md)** — 工作台各功能使用指南
- **[部署说明.md](部署说明.md)** — 生产部署、备份迁移、常见问题
- **[CLAUDE.md](CLAUDE.md)** — 技术架构、代码结构、配置说明（供开发者/AI 参考）

## 测试

```bash
cd ai-tutor-system && python -m pytest tests/ -v
```

## 技术栈

- **后端**：Python 3.12+, FastAPI, Uvicorn
- **AI**：MiniMax API（文本生成、VLM 图片理解）
- **RAG**：RAG-Anything / LightRAG（内置，无需额外安装）
- **Embedding/Rerank**：硅基流动（BAAI/bge-m3, BAAI/bge-reranker-v2-m3）
- **前端**：原生 HTML/CSS/JS（SPA，无框架依赖）
