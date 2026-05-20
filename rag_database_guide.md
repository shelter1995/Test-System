# RAG 知识库使用指南

本项目的知识库服务位于 `rag-anything-api/`，默认端口为 `8003`。用户可见能力统一为传统 RAG（向量检索 + 重排），不再提供 RAG-Anything 引擎切换入口。

## 常用接口

- `GET /db/list`：查看知识库列表。
- `POST /db/register`：创建或更新知识库。
- `GET /db/{db_id}/documents`：查看知识库中的文档状态。
- `POST /ingest/upload`：上传文件并后台导入知识库。
- `GET /ingest/progress/{task_id}`：订阅上传导入进度。
- `POST /db/{db_id}/documents/{sha256}/retry`：重试失败文档。
- `POST /search`：在指定知识库中检索。
- `POST /context`：获取生成和对练使用的知识库上下文。
- `POST /query`：检索并生成知识库问答。
- `POST /kb/chat`：知识库多轮问答。
- `GET /settings/models`：读取模型配置。
- `GET /settings/providers`：读取模型供应商和候选模型。
- `PUT /settings/models`：保存模型配置。
- `POST /settings/models/test`：测试当前或已保存模型配置。

## 解析依赖

- `MinerU`：扫描 PDF、复杂 PDF、图片 OCR 解析
- `LibreOffice`：`.doc/.xls/.ppt` 老 Office 格式转换
- `ffmpeg`：视频抽取音轨
- `openai-whisper`：音频/视频语音转写

## 支持格式

- 文档：`.pdf`、`.doc`、`.docx`、`.xls`、`.xlsx`、`.ppt`、`.pptx`、`.txt`、`.md`、`.csv`
- 图片：`.png`、`.jpg`、`.jpeg`、`.bmp`、`.tiff`、`.webp`
- 音频：`.mp3`、`.wav`、`.flac`、`.aac`、`.ogg`、`.m4a`、`.wma`
- 视频：`.mp4`、`.avi`、`.mkv`、`.mov`、`.webm`、`.wmv`、`.m4v`

传统 RAG 使用硅基流动嵌入和重排模型时，默认按 10 条文本一批提交嵌入请求，并在批次之间等待 1 秒。遇到 429 TPM 限流时，系统会按服务端 `Retry-After` 或退避策略重试。

可调参数：

- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_BATCH_INTERVAL`
- `EMBEDDING_RETRY_ATTEMPTS`
- `EMBEDDING_RETRY_BASE_DELAY`
- `KB_QUERY_REWRITE_ENABLED`
- `KB_RETRIEVAL_CANDIDATES`
- `KB_FINAL_CONTEXTS`
- `KB_MIN_SCORE`

## 存储位置

- 上传文件：`rag-anything-api/storage/raganything/files/{数据库ID}/`
- 传统 RAG 存储：`rag-anything-api/storage/traditional_rag/{数据库ID}/traditional.sqlite`
- 历史 RAG-Anything 存储：`rag-anything-api/storage/raganything/{数据库ID}/rag_storage/`
- MinerU 输出：`rag-anything-api/output/{数据库ID}/`
- 知识库注册表：`rag-anything-api/storage/databases.json`

## 状态与重试

文档状态以 `databases.json` 为准：

- `processing`：后台仍在处理
- `已导入`：导入完成
- `partial_success`：分段恢复部分成功，仍需检查失败分段
- `error`：导入失败，可点击「重试」

前端点击「重试」后会禁用按钮并写入上传日志。解析链路会按文件类型自动选择对应解析器，不需要用户手动切换引擎。

## 历史兼容说明

系统内部仍兼容历史 RAG-Anything 数据目录和索引结构，用于旧数据平滑迁移与读取，但该兼容能力不作为用户操作选项暴露。

可通过 `GET /status` 查看当前媒体依赖检测结果。
