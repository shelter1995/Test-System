# RAG-Anything 迁移设计规格

**日期**: 2026-05-06
**状态**: 已批准
**方案**: 方案 B — 并行运行

---

## 1. 背景与目标

### 1.1 现有系统

- **rag-anything-api**（端口 8003）：基于 RAG-Anything/LightRAG 的知识库服务
- **ai-tutor-system**（端口 8002）：AI话术陪练系统，通过 HTTP 调用 rag-anything-api

### 1.2 迁移目标

将 RAG-Anything（基于 LightRAG 的知识图谱+向量混合检索）作为新服务并行部署，通过配置切换对比效果。

### 1.3 关键决策

| 决策点 | 选择 |
|--------|------|
| 索引 LLM | MiniMax-M2.7 |
| Embedding | 硅基流动 bge-m3 API |
| 多数据库 | 单实例 + 标签过滤 |
| 旧系统 | 已删除 |
| 部署方案 | 单服务运行 |

---

## 2. 架构设计

```
┌─────────────────────────┐
│   ai-tutor-system (8002) │  ← 不改动
│   tutor_backend.py       │
└──────────┬──────────────┘
           │ RAG_SERVICE_URL 固定指向 8003
           │
           ▼
┌──────────────────────┐
│ rag-anything-api      │
│ (8003)                │
│ RAG-Anything/LightRAG │
└──────────────────────┘
```

**服务入口**：`ai-tutor-system/tutor_config.py` 中的 `RAG_SERVICE_URL` 统一为 `http://localhost:8003`。
旧服务已删除，不再保留双服务切换路径。

---

## 3. rag-anything-api 服务

### 3.1 目录结构

```
rag-anything-api/
├── app.py              # FastAPI 主服务
├── adapters.py         # 国产 AI 适配层
├── config.py           # 配置管理
├── .env                # API 密钥
├── requirements.txt    # 依赖
├── start.py            # 启动脚本
└── storage/            # LightRAG 存储目录
    └── lightrag/
```

### 3.2 REST 接口（与 rag-anything-api 兼容）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 系统状态 |
| `/ai_enhanced_search` | POST | AI增强搜索（主接口） |
| `/search` | POST | 语义搜索 |
| `/query` | POST | RAG增强查询 |
| `/status` | GET | 详细状态 |
| `/db/list` | GET | 数据库列表 |
| `/db/stats` | GET | 统计信息 |

### 3.3 适配层

`adapters.py`：
- `minimax_llm_func()` — 把 MiniMax API 包装为 LightRAG 的 `llm_model_func`
- `siliconflow_embedding_func()` — 把硅基流动 API 包装为 LightRAG 的 `embedding_func`

`app.py`：
- 把 RAG-Anything 的 `aquery()` 结果转换为现有 JSON 格式
- 实现 metadata 过滤逻辑（按 database_id）

---

## 4. 知识库设计

### 4.1 单实例 + 标签过滤

一个 RAG-Anything 实例，文档入库时标记来源：

```python
metadata = {
    "database_id": "business_video_ringtone",
    "source": "文件名.pdf",
    "import_time": "2026-05-06"
}
```

查询时通过 `database` 参数过滤。

### 4.2 数据迁移

1. **导出**：从 LightRAG 导出所有文档文本 + metadata → JSON
2. **导入**：调用 RAG-Anything 重新索引
3. **验证**：检查 RAG-Anything 返回结果

### 4.3 数据库优先级

| 数据库 | 优先级 | 说明 |
|--------|--------|------|
| business_video_ringtone | 高 | 陪练系统主要使用 |
| ccs_gyl | 中 | CCS工程 |
| keyexams | 中 | 客业考题 |
| quantum | 低 | 已禁用 |

---

## 5. 错误处理与降级

### 5.1 LLM 超时降级链

索引和查询阶段的 LLM 调用采用逐级降级策略：

```
MiniMax-M2.7（超时）
    ↓ 自动降级
MiniMax-M2.5（超时）
    ↓ 通知用户
询问是否回退到纯向量检索模式
```

**实现逻辑**：
1. 每次请求优先调用 MiniMax-M2.7，超时阈值 120 秒
2. 超时后自动重试 1 次
3. 仍超时，降级到 MiniMax-M2.5，超时阈值 90 秒
4. MiniMax-M2.5 超时后重试 1 次
5. 仍超时，返回错误响应，前端提示用户："大模型调用超时，是否切换到向量检索模式？"
6. 用户确认后，本次会话降级到 `naive` 模式（纯向量检索，不依赖 LLM）

**不持久化降级状态**：每次新请求都从 MiniMax-M2.7 开始尝试，降级仅影响当前请求，不记录状态。下一次请求仍然使用最优模型。

### 5.2 Embedding 超时处理

**优先使用硅基流动 API，通过分批请求避免超时**：

```
文本列表 → 分批（每批 ≤ 20 条） → 逐批调用 API → 合并结果
```

- 单批超时阈值 30 秒
- 单批超时后重试 1 次
- 仍失败则降级到本地 Sentence Transformers（仅当 API 完全不可用时）
- 每次新请求重新尝试 API，不持久化降级状态

**分批逻辑**：
```python
def siliconflow_embedding_func(texts: List[str], batch_size: int = 20) -> List[List[float]]:
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        # 调用 API，超时 30 秒，失败重试 1 次
        embeddings = call_api_with_retry(batch)
        all_embeddings.extend(embeddings)
    return all_embeddings
```

### 5.3 其他降级场景

| 场景 | 降级方案 |
|------|---------|
| 知识图谱构建失败 | 降级到 `naive` 模式（纯向量检索） |
| 查询延迟过高 | 添加结果缓存（TTL 5分钟） |

### 5.4 回退机制

旧服务已删除，回退路径不再维护。后续问题应直接在 `rag-anything-api` 的 8003 服务内修复。

---

## 6. 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `rag-anything-api/app.py` | FastAPI 主服务 |
| 新建 | `rag-anything-api/adapters.py` | AI 适配层 |
| 新建 | `rag-anything-api/config.py` | 配置 |
| 新建 | `rag-anything-api/.env` | API 密钥 |
| 新建 | `rag-anything-api/requirements.txt` | 依赖 |
| 新建 | `rag-anything-api/start.py` | 启动脚本 |
| 克隆 | `RAG-Anything/` | RAG-Anything 源码 |
| 修改 | `ai-tutor-system/tutor_config.py` | 添加 RAG_SERVICE_URL 切换说明注释 |
| 不变 | `ai-tutor-system/tutor_backend.py` | 无需改动 |
| 不变 | `rag-anything-api/` | 保留备份 |

---

## 7. 验证标准

### 7.1 接口兼容性

```bash
# 所有现有接口正常响应
curl -X POST http://localhost:8003/ai_enhanced_search \
  -H "Content-Type: application/json" \
  -d '{"query": "商务视频彩铃价格", "database": "business_video_ringtone"}'

curl http://localhost:8003/status
```

### 7.2 端到端测试

1. 启动 rag-anything-api（8003）
2. 修改 ai-tutor-system 的 RAG_SERVICE_URL 为 8003
3. 启动 ai-tutor-system（8002）
4. 完成一次完整陪练流程：选场景 → 对话 → 评估 → 报告

### 7.3 效果对比

使用典型查询词验证新知识库：
- 相关性
- 准确性
- 响应时间

---

## 8. 时间估算

| 阶段 | 预计时间 |
|------|---------|
| 环境准备（安装依赖、克隆源码） | 1-2 天 |
| 适配层开发 | 2-3 天 |
| 知识库迁移 | 1-2 天 |
| 集成测试 | 1 天 |
| 清理文档 | 0.5 天 |
| **总计** | **5.5-8.5 天** |

