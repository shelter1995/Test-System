# AI 话术陪练系统优化设计

日期: 2026-05-12 | 状态: 已确认

## 问题诊断

当前陪练系统存在以下核心问题：

| # | 问题 | 根因 |
|---|------|------|
| 1 | 前端交互体验差 | 无流式输出，用户发送消息后面对空白等待 30-60s |
| 2 | 问答响应慢 | RAG检索 + AI生成 + AI评估串行执行，一次性返回 JSON |
| 3 | 历史记录查询太简单 | 仅时间倒序列表，无搜索/筛选/详情展开 |
| 4 | 评估系统不透明 | 用户只看到总分，不清楚评分维度、依据、知识库状态 |
| 5 | 后端代码需拆分 | tutor_backend.py 单文件 1155 行，逻辑耦合 |

## 优先级

用户确认：**#1 + #2 最优先**（核心体验问题）。#3、#4 为第二阶段。#5 与 #1#2 同步进行（流式管线需要干净的后端拆分）。

---

## 一、架构变更

### 1.1 后端拆分

当前 `tutor_backend.py`（1155 行）拆为 4 个文件：

```
ai-tutor-system/
├── tutor_backend.py          # FastAPI app + 路由 + 启动 (~100行)
├── tutor_config.py           # 配置（不变）
├── tutor_models.py（新建）    # Pydantic 模型 + SSE 事件类型 (~80行)
├── tutor_services.py（新建）  # 业务逻辑层 (~350行)
│   ├── RAGService            # 知识库检索（复用 rag_client.py）
│   ├── AIService             # MiniMax 调用（流式+非流式）
│   ├── SessionManager        # 会话 CRUD + 过期清理
│   └── ReportGenerator       # 报告生成 + 兜底逻辑
└── tutor_streaming.py（新建） # SSE 管线编排器 (~200行)
    ├── StreamingPipeline     # 编排 RAG→生成→评估 事件流
    ├── EventEmitter          # SSE 事件格式化
    └── handle_chat_stream()  # 核心流式处理函数
```

**设计原则：**
- `tutor_services.py` 中各服务**无状态**，可独立单元测试
- `tutor_streaming.py` 依赖 services，负责事件序列编排
- `tutor_backend.py` 只负责路由 → 调用 streaming → 返回 SSE 响应
- 复用已有的 `rag_client.py`（当前 tutor_backend.py 使用裸 requests，未用该模块）

### 1.2 SSE 流式管线

**一轮对话的完整事件流：**

```
用户发送消息 → POST /chat/stream (SSE)
  │
  ├─ [0.0s] event: status  {"stage":"rag_searching"}
  │   前端: 输入框上方显示进度条 "检索知识库中..."
  │
  ├─ [~3s]  event: status  {"stage":"ai_generating"}
  │   前端: 显示 AI 打字气泡 + 三点动画
  │
  ├─ [~5s]  event: token  {"delta":"你好，我是XX公司..."}
  │   event: token  {"delta":"最近在考虑..."}
  │   ...（持续推送，直到生成完成）
  │   前端: 逐字追加到消息气泡（打字机效果）
  │
  ├─ [~15s] event: done  {"round":3}
  │   🔓 释放输入框！用户可立即开始下一轮
  │
  └─ [~25s] event: evaluation  {"overall_score":82,...}
       ← 异步进行，不阻塞对话
       前端: 评分卡片从下方滑入
```

**关键设计决策：**

1. **done 事件即释放输入框** — AI 回复最后一个 token 推送完毕后，用户即可发下一轮。评分不参与阻塞逻辑。

2. **评分异步后台运行** — evaluation 在 done 之后独立计算。如用户在评分完成前发送新消息：
   - 前端 `AbortController.abort()` 断开 SSE 连接
   - 后端检测到客户端断开 → 停止评分计算
   - 新请求创建新 SSE 连接，旧评分结果丢弃
   - 始终只显示最新一轮的评分卡片

3. **MiniMax 流式调用** — 使用 `POST /v1/text/chatcompletion_v2` + `"stream": true`，后端解析 SSE 响应，提取 delta 作为 token 事件转发给前端。

---

## 二、前端 UI 改造

### 2.1 聊天页

| 元素 | 当前 | 优化后 |
|------|------|--------|
| 进度反馈 | 无 | 阶段指示器（检索中/生成中），进度条+文字，2-3s 后消失 |
| AI 回复 | 一次性显示 | 打字机效果逐字追加，末尾闪烁光标 |
| 发送按钮 | AI 生成中禁用，返回后恢复 | 同前，但 done 事件即恢复，不等评分完成 |
| 错误处理 | console.error + alert | toast 通知 + 自动重试入口 |

### 2.2 非阻塞评分

- `done` 事件后立即调用 `enableInput()`，恢复发送按钮和输入框
- 评分到达时，如果当前无新消息发送中 → 卡片滑入
- 用户开始新一轮 → `abortPendingEvaluation()`，断开旧 SSE，创建新连接

### 2.3 信息看板改进

- 评分区域：显示最新一轮的评分卡片（含 5 维度条形图），旧卡片被替换
- 知识库状态：显示本轮的 RAG 检索情况（检索到 X 条 / 为空）

---

## 三、历史记录增强

### 3.1 列表增强

- 每条记录：场景标签 + 产品名 + 轮次数 + 评分配色指示（绿 80+/黄 60-79/红 <60）
- 搜索框：模糊搜索（产品名、场景名、客户单位）
- 筛选器：场景类型、评分范围、日期范围

### 3.2 内嵌详情

点击列表项展开（不跳页）：
- 对话记录回放（可滚动）
- 五维度评分条形图
- AI 改进建议列表

---

## 四、评估透明度

### 4.1 评估维度可视化

- 每轮评估卡片：总分 + 5 维度条形图（开场/需求挖掘/产品介绍/异议处理/促成）
- 每个维度悬停显示 AI 具体反馈文字
- 知识库来源标注："基于 X 条知识库内容评估"

### 4.2 知识库状态指示

- 评估卡片中显示本轮 RAG 检索的片段数和来源
- "知识库为空"时明确标注，让用户知道评分的可信度

---

## 五、实施计划

### Phase 1：后端拆分 + SSE 流式管线（核心）
- [ ] 新建 `tutor_models.py`
- [ ] 新建 `tutor_services.py`（RAGService + AIService + SessionManager + ReportGenerator）
- [ ] 新建 `tutor_streaming.py`（StreamingPipeline + SSE 事件发射器）
- [ ] 重构 `tutor_backend.py`（精简为路由 + 启动）
- [ ] 新建 `/chat/stream` SSE 端点
- [ ] MiniMax 流式调用（stream: true）
- [ ] 确保现有 15 个测试通过

### Phase 2：前端流式渲染 + 非阻塞评分
- [ ] 重写 `app_with_health_check.js`（EventSource + AbortController）
- [ ] 打字机效果 + 阶段指示器
- [ ] 非阻塞评分（done 即释放输入框）
- [ ] 错误降级处理（toast + 重试）

### Phase 3：历史记录 + 评估可视化
- [ ] 历史列表搜索/筛选/展开详情
- [ ] 五维度评分条形图
- [ ] 知识库来源标注

---

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| MiniMax `stream: true` 兼容性未知 | Phase 1 首步验证流式 API，如不可用则回退到模拟流式（分句推送） |
| SSE 连接管理复杂 | 前端单连接原则（一个 AbortController），后端检测断开后清理 |
| 拆分后现有测试失败 | 保持 API 契约不变，逐步迁移，每步跑测试 |
| Windows 环境下 SSE 稳定性 | 使用 FastAPI StreamingResponse + 标准 SSE 格式，跨平台兼容 |
