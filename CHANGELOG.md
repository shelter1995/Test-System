# Change Log

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
