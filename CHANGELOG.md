# Change Log

## 2026-05-21

### 文档与依赖整理

- 更新 clone 后启动流程，明确 `.venv` 创建、依赖安装、`.env.example` 复制和一键启动顺序。
- 统一文档表述：用户可见知识库能力为传统 RAG，历史 RAG-Anything 数据仅作为内部兼容读取能力。
- 同步支持格式清单，补充 `.pptx`、旧 Office、图片、音频和视频解析说明。
- 补充说明传统 RAG 当前视频解析依赖音轨转写，无音频视频的抽帧与画面理解作为后续功能规划。
- 更新 RAG 与 Tutor 运行依赖清单，补充上传表单、PPTX、OCR/转写相关依赖，移除 Tutor 侧未使用的本地向量化依赖。
- 更新 `.env.example`，补充传统 RAG、知识库问答、内容生成和本地解析程序路径配置项。

## 2026-05-20

### 人工测试修复

- 修复知识库页面切换不同知识库时右侧列表宽度抖动、页面闪烁的问题。
- 修复知识库问答页面的知识库选择框错位问题，改为自定义下拉组件。
- 修复知识库问答回答卡片高度被压缩导致内容显示不完整的问题。
- 优化查询内容与回答内容的视觉区分，降低长文本和来源依据重叠风险。
- 点击失败文档「重试」时增加前端状态反馈和上传日志提示，避免无响应感。

### 模型设置

- 调整模型设置的保存和测试逻辑：保存后刷新可恢复配置，测试连接优先使用当前表单内容，未填写的新密钥则使用已保存密钥。
- 模型设置保存后会刷新后端运行时配置，其他页面重试、上传和查询可读取最新模型状态。
- 模型下拉框补充常用模型选项，同时保留手动填写模型名称能力。

### 传统 RAG

- 传统 RAG 嵌入请求支持批量大小、批次间隔和 429 限流重试配置，降低一次性上传多篇长文时的 TPM 限流失败率。
- 默认嵌入批量大小调整为 10，批次间隔为 1 秒，429 响应会按 `Retry-After` 或退避策略重试。
- 明确旧版 `.xls` 不属于传统 RAG 直接支持格式，需另存为 `.xlsx` 或改用 RAG-Anything 高级解析。

### RAG-Anything

- 修复 RAG-Anything 分段恢复重试时每个分段创建独立 event loop 的问题，避免 LightRAG 共享锁报 `bound to a different event loop`。
- RAG-Anything 的 MinerU Markdown 分段恢复现在在同一个 async 流程中顺序入库，减少长 PDF 重试时的图谱合并失败。

### 验证

- `.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_management_api.py rag-anything-api\tests\test_raganything_service.py -q`
- `.\.venv\Scripts\python.exe -m compileall rag-anything-api`
- `.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests -q`
- `.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests -q`
- `node --check ai-tutor-system\static\js\knowledge.js`
- `node --check ai-tutor-system\static\js\knowledge-chat.js`

## 2026-05-19

### 传统 RAG 引擎

- 新增传统 RAG 引擎作为默认知识库引擎，基于 SQLite 向量存储和文本分块，无需 GPU 或额外依赖。
- 支持 `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.xlsx` 格式的导入和检索。
- 知识库列表和文档列表显示引擎类型标签（传统 RAG / RAG-Anything）。
- 通过 `DEFAULT_RAG_ENGINE` 环境变量可切换默认引擎。

### 模型配置

- 新增「模型设置」Web 页面，支持在线修改推理、嵌入、重排三组模型的供应商、接口地址、模型名和 API Key。
- 支持 OpenAI-compatible 端点（Ollama、vLLM 等第三方兼容服务）。
- 模型配置通过 API 持久化，修改后实时生效，无需重启服务。

### 知识库问答

- 新增「知识库问答」页面，支持先选库、多轮问答、展示来源依据。
- 知识库查询结果包含来源文件名、片段和相关度评分。

### 启动与打包

- `start_services.bat` 增加启动前健康检查，自动检测端口占用和依赖完整性。
- 新增桌面快捷方式脚本 `packaging/create_shortcut.ps1`。
- 新增便携打包脚本 `packaging/package_windows.ps1`，产出包含完整虚拟环境的 Windows 便携包。
- 便携包位于 `dist-portable/Test-System-Portable.zip`。

### 文档

- 更新 README.md，新增知识库引擎、模型配置、桌面快捷方式、便携打包说明。
- 更新 SETUP.md，新增模型配置、引擎切换、便携打包等章节。

## 2026-05-14

### 项目管理

- 删除 AI 工具专用的 `CLAUDE.md`，避免公开仓库保留本地工具上下文。
- 删除 `docs/superpowers/` 下的内部计划和设计草稿，公开仓库仅保留正式项目文档。
- 更新 `.gitignore`，忽略后续生成的 `CLAUDE.md` 和 `docs/superpowers/`。
- 新增根目录 `README.md`，统一说明项目用途、服务结构、启动方式、依赖和常用命令。
- 删除子目录 `ai-tutor-system/README.md`，避免模块级旧说明与仓库级说明重复。
- 删除已跟踪的 `SESSION.md` 会话记录文件，包括根目录和 `rag-anything-api/` 下的会话记录。
- 更新 `.gitignore`，忽略后续生成的 `SESSION.md` 会话记录文件。

### 修复与优化

- 修复陪练系统逐轮评分不稳定的问题：增强 AI 评分 JSON 解析，支持修复模型偶发输出的缺逗号、截断字符串等格式问题。
- 固定逐轮评分输出结构：无论模型评分、修复结果或 fallback 评分，都会返回开场话术、需求挖掘、产品介绍、异议处理、促成技巧五个评分细项。
- 优化结束对话后的报告生成：优先基于已完成的逐轮评分聚合生成最终报告，减少等待“生成报告中”的时间。
- 将详细报告生成放入后台线程执行，避免阻塞 FastAPI 事件循环。
- 修复知识库误恢复问题：RAG 数据库注册表存在时不再自动扫描磁盘残留目录重新注册已删除知识库。
- 删除知识库时同步清理上传文件、RAG 存储目录和解析输出目录。
- 移除陪练系统对“商务彩铃”知识库的硬编码默认值和产品映射。
- 为 RAG 查询增加超时和本地文本兜底检索，降低外部 embedding 或 LightRAG 查询超时导致知识库不可用的影响。
- 更新 MinerU 启动检查逻辑，改为检测新版 `mineru` CLI。
- 新增 `start_services.bat`，用于一键启动 RAG 服务和陪练系统，并在启动后打开浏览器；脚本使用 ASCII 内容以规避 Windows bat 中文乱码。

### 验证

- `python -m pytest ai-tutor-system\tests -q`
- `.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system`
