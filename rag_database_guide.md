# RAG 知识库使用指南

本项目的知识库服务位于 `rag-anything-api/`，默认端口为 `8003`。服务使用 RAG-Anything、MinerU 和 LightRAG 完成文档解析、图谱构建、向量检索与多模态内容处理。

## 常用接口

- `GET /db/list`：查看知识库列表。
- `POST /db/register`：创建或更新知识库。
- `GET /db/{db_id}/documents`：查看知识库中的文档状态。
- `POST /ingest/upload`：上传文件并后台导入知识库。
- `GET /ingest/progress/{task_id}`：订阅上传导入进度。
- `POST /search`：在指定知识库中检索。
- `POST /context`：获取生成和对练使用的知识库上下文。

## 存储位置

- 上传文件：`rag-anything-api/storage/raganything/files/{数据库ID}/`
- RAG 存储：`rag-anything-api/storage/raganything/{数据库ID}/rag_storage/`
- MinerU 输出：`rag-anything-api/output/{数据库ID}/`
- 知识库注册表：`rag-anything-api/storage/databases.json`

## 音视频支持

音视频解析需要同时满足以下条件：

- `.env` 中启用 `ENABLE_VIDEO_PROCESSING=true` 和 `ENABLE_AUDIO_PROCESSING=true`。
- 系统可执行 `ffmpeg`。
- Python 环境可导入 `openai-whisper`。

可通过 `GET /status` 查看当前媒体依赖检测结果。
