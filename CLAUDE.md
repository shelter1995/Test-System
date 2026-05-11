# Test-System 项目概览

## 项目定位

企业 AI 工作台 —— 集成知识库管理、内容生成、AI 话术陪练的 Web 应用。基于商务视频彩铃场景，但支持任意知识库。

## 架构

```
浏览器 (localhost:8002 静态页面)
    │
    ├── RAG 服务 (localhost:8003)   FastAPI + RAG-Anything + LightRAG
    │   ├── /db/list, /db/stats      知识库管理
    │   ├── /search, /ai_enhanced_search  语义检索
    │   └── /ingest/upload           文件上传 + SSE 进度
    │
    └── Tutor 服务 (localhost:8002)  FastAPI
        ├── /chat, /session/*         话术陪练
        ├── /generation/jobs/*        内容生成
        └── /api/status               健康检查
```

## 目录结构

```
Test-System/
├── ai-tutor-system/           # Tutor 服务 + 前端
│   ├── tutor_backend.py       # FastAPI 主入口（端口8002）
│   ├── tutor_config.py        # 配置（API key、端口、模型）
│   ├── minimax_client.py      # MiniMax API 封装（timeout=300s, retries=2）
│   ├── rag_client.py          # RAG 客户端（并行搜索，timeout=120s）
│   ├── generation_api.py      # 内容生成 API 路由（/generation/*）
│   ├── generation_runner.py   # 生成管线核心（solution + training）
│   ├── static/
│   │   ├── index.html         # 统一工作台 SPA
│   │   ├── css/style.css      # 全局样式（CSS 变量体系）
│   │   └── js/
│   │       ├── api.js          # WorkbenchAPI（fetch 封装）
│   │       ├── navigation.js   # 侧边栏导航
│   │       ├── knowledge.js    # 知识库管理（knowledgeState 全局状态）
│   │       ├── generation.js   # 内容生成模块
│   │       └── app_with_health_check.js  # 陪练模块
│   └── tests/
│       └── test_generation_api.py  # 15 个测试
│
├── rag-anything-api/          # RAG 服务（端口8003）
│   ├── app.py                 # FastAPI 主入口
│   ├── raganything_service.py # RAG 引擎封装
│   ├── progress.py            # SSE 进度追踪
│   └── database_registry.py   # 知识库注册表
│
├── solution-generator-skill/  # 解决方案生成技能定义（SKILL.md）
├── peixun-skill/              # 培训材料生成技能定义（SKILL.md）
└── generation_output/         # 生成产物输出目录（gitignored）
```

## 前端页面

| 页面 | data-page | JS 模块 | 状态 |
|------|-----------|---------|------|
| 总览 | `overview` | — | 占位 |
| 知识库 | `knowledge` | knowledge.js | ✅ 完成 |
| 内容生成 | `generation` | generation.js | ✅ 基本完成 |
| 陪练系统 | `tutor` | app_with_health_check.js | 可用 |
| 历史产物 | `history` | generation.js | ✅ 可用 |

## 内容生成模块（当前重点）

**两种类型**：
- `solution`：RAG 检索 5 路 → SCQA+MECE 结构化方案（温度 0.4）
- `training`：RAG 检索 5 路 → 3 次独立 MiniMax 调用 → 讲义(8000tokens) + 测试题(6000tokens) + README(4000tokens)

**流程**：前端表单 → POST /generation/jobs → RAG 并行检索 → 构建富 prompt → MiniMax 生成 → 保存 .md 到 generation_output/

**前端表单字段**：
- 解决方案：客户单位、决策人职位、客情关系、痛点(3个textarea)、决策偏好(3个select)
- 培训材料：培训主题/对象/时长/目标 + 题型勾选+各自数量 + 难度分布(基础/进阶/挑战%)

**关键参数**：
- MiniMax timeout=300s, retries=2, max_tokens=8000(solution)/8000+6000+4000(training)
- RAG timeout=120s, 并行 5 路 × 每路 top-3 × 每片段 ≤600字
- enable_rerank=False（已传参到 RAG 引擎层）

## 风格规范

- CSS 变量体系：`:root` 定义 primary/secondary/accent/success 等
- 卡片组件：`.panel-card` + `.panel-pad`
- 表单：`.form-control`（input/select）、`.form-textarea`
- 响应式断点：900px（grid 变单列）
- JS 全局状态：`knowledgeState`（knowledge.js）、`WorkbenchAPI`（api.js）

## 启动命令

```bash
# RAG 服务（端口 8003）
cd rag-anything-api && python start.py

# Tutor 服务（端口 8002）
cd ai-tutor-system && python tutor_backend.py

# 浏览器打开 http://localhost:8002
```

## 配置

`.env` 文件需配置：
- `MINIMAX_API_KEY` — MiniMax API 密钥

`tutor_config.py`：
- `MINIMAX_MODEL` = `"MiniMax-M2.7"`
- `RAG_SERVICE_URL` = `"http://localhost:8003"`

## 测试

```bash
cd ai-tutor-system && python -m pytest tests/ -v
# 当前：15 passed
```
