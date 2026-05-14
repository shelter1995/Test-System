# Test-System

AI 销售话术陪练与 RAG 知识库系统。项目由两个本地服务组成：

- `rag-anything-api/`：RAG-Anything 知识库服务，默认端口 `8003`
- `ai-tutor-system/`：AI 话术陪练系统和前端界面，默认端口 `8002`

## 主要功能

- 知识库上传、解析、检索与删除
- 基于知识库的销售话术陪练
- 多场景客户对练，包括价格敏感、技术挑剔、决策谨慎、竞品对比
- 每轮对话评分和最终训练报告
- 一键启动两个服务并打开浏览器页面

## 快速启动

1. 配置环境变量：

   - `rag-anything-api/.env`
   - `ai-tutor-system/.env`

2. 在项目根目录运行：

   ```bat
   start_services.bat
   ```

3. 浏览器访问：

   - 陪练系统：http://localhost:8002
   - RAG API 文档：http://localhost:8003/docs
   - 陪练 API 文档：http://localhost:8002/docs

## 依赖说明

项目需要本地 Python 虚拟环境和外部模型服务：

- MiniMax API：用于陪练对话和评分
- 硅基流动 API：用于 embedding、rerank 等模型调用
- MinerU：用于 PDF/Office 文档解析，文本导入不依赖它

依赖安装和环境配置见 [SETUP.md](SETUP.md)。

## 项目结构

```text
Test-System/
├── README.md
├── CHANGELOG.md
├── SETUP.md
├── start_services.bat
├── ai-tutor-system/
│   ├── tutor_backend.py
│   ├── tutor_services.py
│   ├── static/
│   └── tests/
└── rag-anything-api/
    ├── app.py
    ├── raganything_service.py
    ├── database_registry.py
    └── tests/
```

## 常用命令

运行测试：

```powershell
python -m pytest ai-tutor-system\tests -q
```

编译检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api
```

## 文档

- [SETUP.md](SETUP.md)：环境安装与启动说明
- [CHANGELOG.md](CHANGELOG.md)：项目变更记录
- [使用说明.md](使用说明.md)：业务使用流程
- [部署说明.md](部署说明.md)：部署相关说明
