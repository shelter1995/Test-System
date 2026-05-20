# RAG 知识库使用指南

本项目的知识库服务位于 `rag-anything-api/`，默认端口为 `8003`。服务同时提供传统 RAG 和 RAG-Anything 两条路线：

- **传统 RAG（默认）**：面向快速、稳定的文本分块和向量检索，适合常见办公文档。
- **RAG-Anything（高级）**：面向复杂 PDF、多模态解析、图谱构建和深度语义处理。

## 常用接口

- `GET /db/list`：查看知识库列表。
- `POST /db/register`：创建或更新知识库。
- `GET /db/{db_id}/documents`：查看知识库中的文档状态。
- `POST /ingest/upload`：上传文件并后台导入知识库。
- `GET /ingest/progress/{task_id}`：订阅上传导入进度。
- `POST /db/{db_id}/documents/{sha256}/retry`：重试失败文档。
- `POST /search`：在指定知识库中检索。
- `POST /context`：获取生成和对练使用的知识库上下文。
- `GET /settings/models`：读取模型配置。
- `PUT /settings/models`：保存模型配置。
- `POST /settings/models/test`：测试当前或已保存模型配置。

## 引擎与格式

### 传统 RAG

默认新建知识库使用传统 RAG。支持格式：

- `.txt`
- `.md`
- `.csv`
- `.pdf`
- `.docx`
- `.xlsx`

旧版 `.xls` 不由传统 RAG 直接处理，请另存为 `.xlsx` 后上传，或切换到 RAG-Anything 高级解析。

传统 RAG 使用硅基流动嵌入和重排模型时，默认按 10 条文本一批提交嵌入请求，并在批次之间等待 1 秒。遇到 429 TPM 限流时，系统会按服务端 `Retry-After` 或退避策略重试。

可调参数：

- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_BATCH_INTERVAL`
- `EMBEDDING_RETRY_ATTEMPTS`
- `EMBEDDING_RETRY_BASE_DELAY`

### RAG-Anything

RAG-Anything 适合复杂 PDF、图片、音频、视频和表格/公式/图像混排文档。失败文档点击「重试」时，会优先复用 MinerU 输出的 Markdown 并分段恢复。分段恢复在同一个 async 流程中顺序执行，避免 LightRAG 共享锁跨 event loop 冲突。

## 存储位置

- 上传文件：`rag-anything-api/storage/raganything/files/{数据库ID}/`
- 传统 RAG 存储：`rag-anything-api/storage/traditional_rag/{数据库ID}/traditional.sqlite`
- RAG-Anything 存储：`rag-anything-api/storage/raganything/{数据库ID}/rag_storage/`
- MinerU 输出：`rag-anything-api/output/{数据库ID}/`
- 知识库注册表：`rag-anything-api/storage/databases.json`

## 状态与重试

文档状态以 `databases.json` 为准：

- `processing`：后台仍在处理
- `已导入`：导入完成
- `partial_success`：分段恢复部分成功，仍需检查失败分段
- `error`：导入失败，可点击「重试」

前端点击「重试」后会禁用按钮并写入上传日志。RAG-Anything 重试可能耗时较长，需要等待 MinerU 解析和 LightRAG 图谱入库完成。

## 音视频支持

音视频解析需要同时满足以下条件：

- `.env` 中启用 `ENABLE_VIDEO_PROCESSING=true` 和 `ENABLE_AUDIO_PROCESSING=true`。
- 系统可执行 `ffmpeg`。
- Python 环境可导入 `openai-whisper`。

可通过 `GET /status` 查看当前媒体依赖检测结果。
