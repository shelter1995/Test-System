# 知识库 RAG 体验重构设计

日期：2026-05-20

## 背景

当前项目已经具备传统 RAG 和 RAG-Anything 两套知识库引擎。实际使用中，RAG-Anything 对普通业务文档的处理速度慢、失败率高，而知识库问答的回答质量与 Cherry Studio 相比存在明显差距。

本次重构目标是把用户可见的知识库能力统一到传统 RAG 技术栈上，增强文件解析能力，并把知识库问答升级为更稳定的多阶段检索增强生成链路。

## 目标

1. 前端隐藏 RAG-Anything 类型，用户创建和使用知识库时不再选择引擎。
2. 所有新知识库默认并强制使用传统 RAG。
3. 传统 RAG 增加 PDF、扫描版 PDF、图片、PPT、PPTX、DOC、DOCX、XLS、XLSX、音频、视频等格式的文本提取能力。
4. 知识库问答参考 Cherry Studio 的知识库实现思路，加入多查询召回、候选合并、去重、阈值过滤、重排和引用式回答。
5. 保持现有接口基本兼容，降低对内容生成和销售陪练模块的破坏面。

## 非目标

1. 本阶段不删除 RAG-Anything 源码和历史数据。
2. 本阶段不做视频画面帧理解，只处理视频中的音轨转写文本。
3. 本阶段不引入新的远程向量数据库，继续使用当前 SQLite 向量存储。
4. 本阶段不重写整个前端，只调整知识库管理和问答相关界面。

## 参考 Cherry Studio 的能力

Cherry Studio 的知识库核心链路是：文件进入本地知识库、抽取文本、切分片段、生成 embedding、检索相关片段、可选 rerank、把片段作为上下文交给 LLM 回答。

本项目采用以下可落地部分：

1. embedding 输入长度控制，避免超长片段拖慢或失败。
2. 检索时召回更多候选，再在本地做去重和阈值过滤。
3. 可选 rerank 后再截断最终上下文。
4. 支持多问题或改写查询合并结果，提高命中率。
5. 回答中带来源编号，前端来源依据与回答引用对应。

## 前端设计

### 知识库管理

文件：`ai-tutor-system/static/js/knowledge.js`

调整：

1. 移除“RAG 引擎”下拉框。
2. 创建知识库时不再发送用户选择的 engine，后端默认传统 RAG。
3. 知识库列表和文档列表不再展示“传统 RAG / RAG-Anything”标签。
4. 上传提示统一为：
   `支持格式：PDF、Word(.doc/.docx)、Excel(.xls/.xlsx)、PPT(.ppt/.pptx)、TXT、Markdown、CSV、音频、视频`
5. 上传日志统一展示“正在解析并索引”，不暴露 RAG-Anything 术语。

### 知识库问答

文件：`ai-tutor-system/static/js/knowledge-chat.js`

调整：

1. 来源依据继续显示在右侧。
2. 来源项增加稳定编号，例如“来源 1”“来源 2”。
3. 回答正文可以引用 `[来源 1]`，前端来源面板显示对应文件、片段和相关度。
4. 查询失败时提示更明确：区分知识库为空、解析中、模型调用失败、检索失败。

## 后端设计

### 引擎选择

文件：

1. `rag-anything-api/app.py`
2. `rag-anything-api/database_registry.py`
3. `rag-anything-api/rag_engines/factory.py`

调整：

1. `POST /db/register` 忽略前端传入的 `raganything`，新知识库写入 `engine: "traditional"`。
2. `PUT /db/{db_id}` 不允许通过普通前端流程切换到 RAG-Anything。
3. 旧知识库如果已有 `engine: "raganything"`，暂时保持可读，避免历史数据突然不可用；但 UI 不再提供入口。

### 文件转文本层

文件：`rag-anything-api/rag_engines/traditional/document_loader.py`

设计原则：

1. 传统 RAG 仍然是唯一面向用户的知识库引擎。
2. MinerU 作为文档解析/OCR 后端使用，不作为 RAG-Anything 图谱检索链路使用。
3. 文本型 PDF 走快速解析；扫描版 PDF、乱码 PDF、图片型 PDF、复杂表格/公式 PDF 走 OCR/版面解析。
4. 图片文件进入 OCR/图像描述流程，产出可检索的 Markdown 文本和结构化元数据。

新增或调整解析器：

1. `.txt/.md/.csv`：保留当前逻辑。
2. `.pdf`：先用 `pypdf` 快速抽取文本；如果文本量低、乱码比例高、页面疑似扫描图，自动切换到 MinerU OCR/版面解析。
3. `.docx`：保留段落和表格抽取。
4. `.xlsx`：保留工作表逐行抽取。
5. `.pptx`：新增 `python-pptx` 抽取幻灯片文本、表格文本、备注文本。
6. `.doc`：新增老 Word 格式转换流程，优先通过 LibreOffice/soffice 转为 `.docx` 或 `.pdf` 后抽取文本；缺少转换工具时返回清晰错误。
7. `.xls`：新增老 Excel 格式转换流程，优先通过 LibreOffice/soffice 转为 `.xlsx` 后抽取文本；缺少转换工具时返回清晰错误。
8. `.ppt`：新增老 PowerPoint 格式转换流程，优先通过 LibreOffice/soffice 转为 `.pptx` 或 `.pdf` 后抽取文本；缺少转换工具时返回清晰错误。
9. 音频：`.mp3/.wav/.flac/.aac/.ogg/.m4a` 通过 Whisper 转写文本。
10. 视频：`.mp4/.avi/.mkv/.mov/.webm` 通过 ffmpeg 抽取音轨，再用 Whisper 转写文本。
11. 图片：`.png/.jpg/.jpeg/.bmp/.tiff/.tif/.webp` 通过 MinerU OCR 或后续可配置的视觉模型生成可检索文本。

转换结果应写入临时目录或传统 RAG 存储目录下的派生文本缓存，避免重复上传同一文件时每次都重新转写。

### PDF OCR 与图像处理

新增模块建议：

1. `rag-anything-api/rag_engines/traditional/document_parsers/mineru_parser.py`
2. `rag-anything-api/rag_engines/traditional/document_parsers/media_parser.py`
3. `rag-anything-api/rag_engines/traditional/document_parsers/office_converter.py`

PDF 解析流程：

1. 对 PDF 先执行快速探测：页数、可抽取字符数、乱码比例、是否存在大量图片对象。
2. 如果是普通文本 PDF，使用 `pypdf` 快速抽取，减少处理时间。
3. 如果是扫描版或复杂版式 PDF，调用 MinerU 输出 Markdown/JSON。
4. MinerU 输出中的文本、标题、表格、公式说明、图片标题和脚注进入传统 RAG 分块。
5. 每个 chunk metadata 记录 `page_number`、`block_type`、`bbox`、`parser: mineru`，便于来源展示和后续排查。

图像处理流程：

1. 对图片文件使用 MinerU OCR 提取文字。
2. 如果 MinerU 返回图片描述、表格、标题或脚注，将这些内容合并为 Markdown。
3. 如果图片没有可识别文字，返回“未识别到可索引文本”，不生成空索引。
4. 后续可接入 VLM 生成图片语义描述，但本阶段默认只要求 OCR 和 MinerU 可产出的结构化内容。

解析输出缓存：

1. 缓存 key 使用文件 sha256、解析器名称、解析配置版本。
2. 缓存 Markdown 和必要 JSON 元数据。
3. 文档重试时优先复用缓存；用户删除文档时同步清理对应缓存。

### 依赖检测

文件：`rag-anything-api/config.py`

调整：

1. 检测 `ffmpeg`、`whisper`、`soffice` 或 LibreOffice、`mineru`。
2. `/status` 返回传统 RAG 文件解析依赖状态。
3. 如果缺少依赖，导入对应格式时给出可执行的错误信息，例如：
   `当前环境未检测到 LibreOffice，无法解析 .doc 文件。请安装 LibreOffice 或另存为 .docx 后上传。`
4. 如果缺少 MinerU，扫描版 PDF 和图片导入返回清晰错误；普通文本 PDF 仍可走 `pypdf` 快速路径。

### 检索链路

文件：

1. `rag-anything-api/rag_engines/traditional/engine.py`
2. `rag-anything-api/rag_engines/traditional/vector_store.py`
3. `rag-anything-api/kb_answer.py`

新增检索配置：

1. `KB_QUERY_REWRITE_ENABLED`，默认开启。
2. `KB_RETRIEVAL_CANDIDATES`，默认 20。
3. `KB_FINAL_CONTEXTS`，默认 8。
4. `KB_MIN_SCORE`，默认 0.2，可按模型调节。
5. `KB_CONTEXT_MAX_CHARS`，默认沿用现有上下文长度配置。

查询流程：

1. 根据当前问题和最近历史生成 2-3 个检索查询。
2. 对每个查询分别 embedding 和向量召回。
3. 合并候选结果，按 `document_sha256 + chunk_index` 和文本指纹去重。
4. 低于 `KB_MIN_SCORE` 的结果过滤掉。
5. 如果 rerank 可用，对候选文本重排。
6. 取最终 `KB_FINAL_CONTEXTS` 条上下文。
7. 给每条上下文分配 `source_id`，例如 `来源 1`。

### 回答生成

文件：`rag-anything-api/kb_answer.py`

提示词调整：

1. 明确只基于知识库回答。
2. 要求先给直接结论。
3. 要求在关键句后标注来源编号，例如 `[来源 1]`。
4. 资料不足时说明缺少哪些信息，不编造。
5. 对流程、价格、政策、版本、日期类问题要求逐条列出依据。

响应结构保持兼容，扩展来源字段：

```json
{
  "answer": "...",
  "sources": [
    {
      "source_id": "来源 1",
      "file_name": "产品手册.pdf",
      "snippet": "...",
      "score": 0.72,
      "rerank_score": 0.91,
      "chunk_index": 3,
      "document_sha256": "..."
    }
  ]
}
```

## 错误处理

1. 文件解析失败：文档状态为 `error`，错误信息包含格式、缺失依赖或解析异常。
2. 音视频转写失败：文档状态为 `error`，提示 ffmpeg 或 Whisper 状态。
3. embedding 失败：保留现有限流重试，最终失败时写入文档错误。
4. 问答无结果：返回“当前知识库未找到相关资料”，同时 sources 为空。
5. LLM 回答失败：返回已召回的原文片段兜底答案。

## 测试计划

### 单元测试

1. `test_traditional_document_loader.py`
   - `.pptx` 能抽取幻灯片文本。
   - `.doc/.xls/.ppt` 在缺少 LibreOffice 时返回清晰错误。
   - 扫描版或低文本 PDF 会选择 MinerU 解析路径。
   - 图片文件会选择 MinerU OCR 路径。
   - 缺少 MinerU 时，扫描版 PDF 和图片返回清晰错误。
   - 音频在缺少 Whisper 时返回清晰错误。
   - 视频在缺少 ffmpeg 或 Whisper 时返回清晰错误。

2. `test_traditional_engine.py`
   - 多查询召回会合并候选。
   - 候选结果按 chunk 去重。
   - 低分结果被阈值过滤。
   - rerank 后按重排结果输出。

3. `test_kb_answer.py`
   - prompt 包含来源编号。
   - sources 输出包含 `source_id`、文件名、片段、分数。
   - 无上下文时不编造答案。

### 前端静态检查

1. `node --check ai-tutor-system/static/js/knowledge.js`
2. `node --check ai-tutor-system/static/js/knowledge-chat.js`

### 后端验证

1. `python -m pytest rag-anything-api/tests -q`
2. `python -m compileall -q ai-tutor-system rag-anything-api`

## 推进顺序

1. 先写后端测试，覆盖文件解析和检索链路。
2. 实现传统 RAG 文件转文本扩展。
3. 接入 MinerU 作为传统 RAG 的 PDF OCR 和图片 OCR 解析后端。
4. 实现多阶段检索和问答来源结构。
5. 调整前端知识库管理和问答展示。
6. 更新 README、SETUP 和使用说明中的知识库描述。
7. 跑测试和编译检查。

## 风险与取舍

1. 老 Office 格式依赖 LibreOffice/soffice 转换，环境没有该工具时无法稳定解析；设计上选择清晰失败，而不是静默降级。
2. 音视频转写耗时可能较长，需要保留后台处理和进度刷新。
3. 多查询召回会增加 embedding 和 rerank 调用次数，需要通过候选数量和历史轮数控制成本。
4. 继续使用 SQLite 向量存储适合当前本地部署规模；如果知识库规模明显增长，再单独评估向量数据库。
5. MinerU 对复杂 PDF、扫描版 PDF、表格和图片更可靠，但处理成本高于 `pypdf`；因此采用“快速解析优先，必要时 OCR”的分层策略。

## 验收标准

1. 前端用户看不到 RAG-Anything 选项或标签。
2. 新建知识库全部为传统 RAG。
3. `.pdf/.doc/.docx/.xls/.xlsx/.ppt/.pptx/.txt/.md/.csv/.png/.jpg/.jpeg/.bmp/.tiff/.webp` 可进入传统 RAG 解析流程。
4. 音频和视频可在依赖满足时转写并入库。
5. 扫描版 PDF 和图片在 MinerU 可用时能通过 OCR 产生可检索文本。
6. 知识库问答能返回带来源编号的答案和来源依据。
7. 对同一批文档，问答结果比当前版本更少跑偏，资料不足时更少编造。
8. 相关测试和编译检查通过。
