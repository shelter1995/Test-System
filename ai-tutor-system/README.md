# AI 话术陪练系统

> 本目录为 Test-System 项目的 Tutor 服务子系统。完整项目文档请查看根目录 [README.md](../README.md)。

## 子系统定位

提供 AI 话术陪练、内容生成、统一工作台前端服务，端口 **8002**。

## 快速启动

```bash
# 安装依赖
pip install -r requirements_tutor.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY

# 启动服务
python tutor_backend.py
```

浏览器访问：**http://localhost:8002**（统一工作台，包含知识库、内容生成、陪练系统）

## 文件说明

| 文件 | 说明 |
|------|------|
| `tutor_backend.py` | FastAPI 启动入口（含路由） |
| `tutor_services.py` | RAG/AI/会话/报告 业务逻辑层 |
| `tutor_streaming.py` | SSE 流式管线编排 |
| `tutor_models.py` | Pydantic 数据模型 |
| `generation_api.py` | 内容生成 API 路由 |
| `generation_runner.py` | 解决方案 / 培训材料生成核心 |
| `minimax_client.py` | MiniMax API 封装 |
| `rag_client.py` | RAG 服务 HTTP 客户端 |
| `tutor_config.py` | 场景、评估维度、模型配置 |
| `static/index.html` | 统一工作台 SPA |
| `tests/` | pytest 测试（15 个） |

## 依赖服务

- **RAG 服务** (http://localhost:8003) — 提供知识库检索
- **MiniMax AI API** — 必需，提供对话生成与评估

## API 文档

启动后访问：http://localhost:8002/docs

---

**版本**: v2.1  
**更新时间**: 2026-05
