# Test-System 项目概览

## 项目定位

企业 AI 工作台 —— 集成知识库管理、内容生成、AI 话术陪练的 Web 应用。基于商务视频彩铃场景，但支持任意知识库。

## 架构

```
浏览器 (localhost:8002 静态页面)
    │
    ├── RAG 服务 (localhost:8003)   FastAPI + RAG-Anything + MinerU + LightRAG
    │   ├── /db/list, /db/stats      知识库管理
    │   ├── /search, /query          hybrid 混合检索（向量+图谱）
    │   ├── /context                 轻量上下文提取
    │   └── /ingest/upload           文件上传 + SSE 进度
    │
    └── Tutor 服务 (localhost:8002)  FastAPI
        ├── /chat, /chat/stream      话术陪练（非流式 + SSE 流式）
        ├── /session/start, /session/end, /session/{id}  会话管理
        ├── /scenarios, /scenarios/create  场景管理
        ├── /history                 历史记录
        ├── /generation/jobs/*       内容生成
        └── /api/status              健康检查
```

## 目录结构

```
Test-System/
├── ai-tutor-system/           # Tutor 服务 + 前端
│   ├── tutor_backend.py       # FastAPI 路由 + 启动（~480行，精简版）
│   ├── tutor_config.py        # 配置（API key、端口、模型、场景、评估维度）
│   ├── tutor_models.py        # Pydantic 数据模型 + SSE 事件类型（~86行）
│   ├── tutor_services.py      # 业务逻辑层（~580行）
│   │   ├── RAGService         #   知识库检索（复用 rag_client.py）
│   │   ├── AIService          #   MiniMax 流式/非流式调用 + 评估
│   │   ├── SessionManager     #   会话 CRUD + 列表
│   │   └── ReportGenerator    #   报告生成 + 兜底
│   ├── tutor_streaming.py     # SSE 管线编排器（~240行）
│   │   └── StreamingPipeline  #   RAG检索 → AI流式生成 → 异步评估
│   ├── minimax_client.py      # MiniMax API 封装（timeout=300s, retries=2, stream/非stream）
│   ├── rag_client.py          # RAG HTTP 客户端（并行多查询，timeout=120s）
│   ├── generation_api.py      # 内容生成 API 路由（/generation/*）
│   ├── generation_runner.py   # 生成管线核心（solution + training）
│   ├── static/
│   │   ├── index.html         # 统一工作台 SPA
│   │   ├── css/style.css      # 全局样式（CSS 变量 + flex 布局体系）
│   │   └── js/
│   │       ├── api.js                    # WorkbenchAPI（fetch 封装）
│   │       ├── navigation.js             # 侧边栏导航 + tutor-active 类切换
│   │       ├── knowledge.js              # 知识库管理（knowledgeState 全局状态）
│   │       ├── generation.js             # 内容生成模块
│   │       └── app_with_health_check.js  # 陪练模块（SSE 流式 + 打字机 + 非阻塞评分）
│   └── tests/
│       └── test_generation_api.py  # 15 个测试
│
├── rag-anything-api/          # RAG 服务（端口8003）
│   ├── app.py                 # FastAPI 路由（/search, /query, /ingest 等）
│   ├── config.py              # 环境变量配置（LLM/VLM/Rerank/MinerU）
│   ├── raganything_service.py # RAG-Anything 引擎封装（VLM + Rerank）
│   ├── start.py               # 启动脚本（自动依赖检查）
│   ├── progress.py            # SSE 进度追踪
│   ├── database_registry.py   # 知识库注册表
│   ├── raganything/           # RAG-Anything 引擎源码（内置，18个文件）
│   ├── .env.example           # 配置模板
│   └── requirements.txt       # Python 依赖
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
| 陪练系统 | `tutor` | app_with_health_check.js | ✅ SSE 流式可用 |
| 历史产物 | `history` | generation.js | ✅ 可用 |

## 陪练系统（当前重点）

### 后端架构（Phase 1 重构后）

三层拆分，所有服务无状态可独立测试：

- `tutor_models.py` — Pydantic 模型（ScenarioCreate, SessionStart, ChatMessage, SessionEnd）+ SSEEvent 格式类（7 个静态方法）
- `tutor_services.py` — RAGService（检索+数据库映射）、AIService（流式/非流式生成+评估+开场白）、SessionManager（CRUD+列表）、ReportGenerator（AI报告+兜底）
- `tutor_streaming.py` — StreamingPipeline 编排四阶段：RAG 3路并行检索 → AI 逐 token 流式生成 → done 释放输入框 → 异步评估
- `tutor_backend.py` — 精简为路由层（~480行），`/chat` 保持兼容，`/chat/stream` 新 SSE 端点

### SSE 流式管线

```
POST /chat/stream
  → event: status   {stage:"rag_searching"}    前端: 阶段指示器
  → event: token    {delta:"你好..."}           前端: 打字机逐字追加
  → event: done     {round:3}                  前端: 释放输入框，用户可发下一轮
  → event: evaluation {overall_score:82,...}   前端: 评分卡片滑入（异步，不阻塞输入）
```

### 前端交互

- **打字机效果**：`fetch()` + `ReadableStream` 解析 SSE，token 事件逐字追加
- **非阻塞评分**：done 后立即启用输入框，评分通过独立请求异步获取
- **阶段指示器**：检索中 / 生成中 进度条，自动消失
- **评估卡片**：五维条形图 + 评分依据 + 知识库来源标注
- **Toast 通知**：替代 alert，支持 info/error/success
- **右侧面板**：累计评分 + 知识库状态，不含实时建议（已精简）

### 历史抽屉

- 从右侧滑入（400px），带半透明遮罩，点击遮罩关闭
- 搜索框 + 场景筛选 + 评分配色（绿≥80 / 黄60-79 / 红<60）
- 点击展开：最近对话摘要 + 五维评分条形图 + 知识库状态

### 报告页

- 顶栏 `← 返回设置` 按钮
- 五维评分条形图 + 亮点/待改进/建议
- 调用 AI 生成详细报告（`detail_level=detailed`）

### 页面布局（flex 体系）

三页面（开始/对话/报告）通过 flex 链填满可用空间：
`.content.tutor-active(overflow:hidden)` → `.page-section(flex:1)` → `#tutorApp(flex:1)` → `.page(flex:1)` → 内容区

开始页和报告页内部可滚动（`overflow-y: auto`），聊天页由 `.chat-messages` 独立滚动。

### 已知注意事项

- SSE 流式需要重启 Tutor 服务才能生效（代码已就绪）
- AI 名称混淆已通过 system prompt 约束（禁止自编姓名）
- 评估和报告 prompt 已全部中文化，包含评分依据要求

## 内容生成模块

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
- RAG 默认查询模式=hybrid（向量+图谱融合），支持 naive/local/global/hybrid/mix 五种
- Rerank 可选开启（硅基流动 BAAI/bge-reranker-v2-m3），`ENABLE_RERANK=true`
- VLM 图片理解可选开启（MiniMax VL），`ENABLE_VLM=true`，自动将检索到的图片提交 VLM 看图回答

## 风格规范

- CSS 变量体系：`:root` 定义 primary/secondary/accent/success/warning/info 等
- 卡片组件：`.panel-card` + `.panel-pad`
- 表单：`.form-group input/select/textarea`（统一样式，padding: 0.5rem 0.75rem）
- 陪练布局：flex 贯穿全链，无固定 calc 高度
- 响应式断点：900px（grid 变单列）
- JS 全局状态：`knowledgeState`（knowledge.js）、`WorkbenchAPI`（api.js）
- SSE 流式：`state.abortController` 管理连接，`state.lastKnowledgeCount` 传递知识库状态
- 布局切换：`navigation.js` 中 `tutor-active` 类控制陪练页面无 padding 紧凑模式

## 启动命令

```bash
# RAG 服务（端口 8003）
cd rag-anything-api && python start.py

# Tutor 服务（端口 8002）
cd ai-tutor-system && python tutor_backend.py

# 浏览器打开 http://localhost:8002
```

> 完整部署说明（首次使用、环境配置、依赖安装、验证步骤）见 [SETUP.md](SETUP.md)

## 配置

> 复制 `.env.example` 为 `.env` 并填入密钥。完整模板见各目录下的 `.env.example`。

### Tutor 服务 — `ai-tutor-system/.env`

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINIMAX_API_KEY` | 必填 | MiniMax API 密钥 |
| `MINIMAX_MODEL` | `MiniMax-M2.7` | 文本生成模型 |
| `RAG_SERVICE_URL` | `http://localhost:8003` | RAG 服务地址 |
| `RAG_REQUEST_TIMEOUT` | `90` | RAG 请求超时（秒） |
| `TUTOR_SERVICE_HOST` | `0.0.0.0` | Tutor 监听地址 |
| `TUTOR_SERVICE_PORT` | `8002` | Tutor 监听端口 |

### RAG 服务 — `rag-anything-api/.env`

RAG-Anything 引擎源码已内置在 `rag-anything-api/raganything/` 中，无需额外安装。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINIMAX_API_KEY` | 必填 | MiniMax LLM（文本生成） |
| `MINIMAX_MODEL_M27` | `MiniMax-M2.7` | 主 LLM 模型 |
| `SILICONFLOW_API_KEY` | 必填 | 硅基流动 Embedding + Rerank |
| `SILICONFLOW_MODEL` | `BAAI/bge-m3` | Embedding 模型 |
| `DEFAULT_QUERY_MODE` | `hybrid` | 查询模式：naive / local / global / hybrid / mix |
| `ENABLE_VLM` | `false` | 开启 MiniMax Coding Plan 图片理解 |
| `VLM_BASE_URL` | `https://api.minimaxi.com` | VLM 国内站；国际站用 `api.minimax.io` |
| `ENABLE_RERANK` | `false` | 开启硅基流动检索重排序 |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Rerank 模型 |
| `PARSER` | `mineru` | 文档解析引擎 |
| `MINERU_BACKEND` | `pipeline` | MinerU 后端 |
| `CHUNK_SIZE` | `1200` | 文档分块大小（tokens） |
| `RAG_SERVICE_PORT` | `8003` | RAG 监听端口 |

密钥获取：
- MiniMax：https://platform.minimaxi.com
- 硅基流动：https://siliconflow.cn

## 测试

```bash
cd ai-tutor-system && python -m pytest tests/ -v
# 当前：15 passed
```
