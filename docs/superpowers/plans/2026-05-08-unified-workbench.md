
# 统一工作台实施计划

> **给明天执行的 agent/开发者：** 实施时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行。每个步骤使用 checkbox 跟踪。

**目标：** 在现有 `Test-System` 上建设统一网页工作台，把知识库管理、文件上传、内容生成、AI 话术陪练和历史产物整合到一个入口，界面风格参考 `D:\GitHub_WorkSpace\Exam-Generator`。

**架构：** 保持现有双服务结构，不引入新的前端框架。`rag-anything-api` 继续作为知识库服务运行在 8003 端口；`ai-tutor-system` 继续作为陪练和工作台服务运行在 8002 端口。前端使用原生 HTML/CSS/JS 拆分模块，后端用 FastAPI 增加必要接口。

**技术栈：** FastAPI、Pydantic、pytest、FastAPI TestClient、原生 HTML/CSS/JavaScript、现有 RAG-Anything 服务层、现有 MiniMax 内容生成脚本。

---

## 一、总体顺序

按下面顺序执行，保证每一阶段都能单独验证：

1. 扩展 RAG 知识库注册表能力。
2. 增加 RAG 知识库管理 API：创建、更新、文件列表、网页上传。
3. 建立统一工作台壳：侧边栏、顶部状态、页面切换。
4. 实现知识库管理页面。
5. 增加内容生成 API：方案、讲义、测试题、README。
6. 实现内容生成页面和历史产物下载。
7. 改造陪练系统界面，并支持显式选择知识库。
8. 更新文档并完成端到端验证。

明天优先完成 **任务 1-4**。这四项完成后，就会有一个能打开、能看知识库、能创建知识库、能上传文件的基础工作台。

---

## 二、文件边界

### RAG 服务

- 修改 `D:\GitHub_WorkSpace\Test-System\rag-anything-api\database_registry.py`
  - 支持知识库描述、状态更新、文档列表。
- 修改 `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
  - 新增 `/db/register`、`/db/{db_id}`、`/db/{db_id}/documents`、`/ingest/upload`。
- 新增测试 `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_database_management_api.py`
  - 用 fake service 测 API 合同，不调用真实 RAG-Anything。

### 生成服务

- 新建 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\generation_runner.py`
  - 包装现有 `run_skill_compliance_suite.py`，负责执行生成任务并记录结果。
- 新建 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\generation_api.py`
  - 提供生成任务、任务查询、历史产物列表、下载接口。
- 修改 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tutor_backend.py`
  - 挂载 `generation_api` router。
- 新增测试 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tests\test_generation_api.py`
  - 测生成任务创建、任务查询、产物列表。

### 前端工作台

- 重写/改造 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\static\index.html`
  - 统一入口：总览、知识库、内容生成、陪练系统、历史产物。
- 修改 `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\static\css\style.css`
  - 统一视觉风格，参考 `Exam-Generator` 的浅色、卡片、表单、Tab/侧边导航风格。
- 新建前端模块：
  - `static\js\api.js`：统一 fetch 封装和服务地址。
  - `static\js\navigation.js`：页面切换和导航激活状态。
  - `static\js\health.js`：服务健康检查。
  - `static\js\knowledge.js`：知识库列表、创建、上传、文件列表。
  - `static\js\generation.js`：生成表单、生成任务、历史产物。
  - `static\js\tutor.js`：陪练页面逻辑。

### 文档

- 修改 `D:\GitHub_WorkSpace\Test-System\使用说明.md`
- 修改 `D:\GitHub_WorkSpace\Test-System\未来优化方向.md`

---

## 任务 1：扩展 RAG 知识库注册表

**文件：**

- 修改：`rag-anything-api\database_registry.py`
- 新增/修改测试：`rag-anything-api\tests\test_database_management_api.py`

### 步骤

- [ ] 写测试：`register_database()` 应保存 `description`、`working_dir`、`output_dir`。
- [ ] 写测试：`update_database()` 应能更新 `name`、`description`、`status`。
- [ ] 写测试：`list_documents()` 应返回指定知识库的文件列表。
- [ ] 运行测试确认失败：

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python -m pytest tests\test_database_management_api.py -v
```

- [ ] 修改 `DatabaseRegistry.register_database()`：
  - 增加参数 `description: str | None = None`
  - 创建和更新时都写入 `description`
- [ ] 新增 `DatabaseRegistry.update_database()`：
  - 参数：`database_id`、`name`、`description`、`status`
  - 找不到库时抛 `KeyError`
- [ ] 新增 `DatabaseRegistry.list_documents()`：
  - 返回 `documents` 列表
  - 找不到库时抛 `KeyError`
- [ ] 再次运行测试，确认通过。
- [ ] 提交：

```powershell
git add rag-anything-api\database_registry.py rag-anything-api\tests\test_database_management_api.py
git commit -m "feat: extend rag database registry metadata"
```

---

## 任务 2：增加 RAG 知识库管理 API

**文件：**

- 修改：`rag-anything-api\app.py`
- 修改测试：`rag-anything-api\tests\test_database_management_api.py`

### API 目标

- `POST /db/register`
  - 创建或登记知识库。
  - 请求体：`id`、`name`、`description`
- `PUT /db/{db_id}`
  - 更新知识库名称、描述、状态。
- `GET /db/{db_id}/documents`
  - 查询知识库已导入文件。
- `POST /ingest/upload`
  - multipart 上传文件并导入指定知识库。

### 步骤

- [ ] 写 API 测试：创建知识库。
- [ ] 写 API 测试：更新知识库。
- [ ] 写 API 测试：查询知识库文件列表。
- [ ] 写 API 测试：multipart 上传 `.txt` 文件，fake service 收到 `ingest_file(database, path)`。
- [ ] 运行测试确认失败。
- [ ] 在 `app.py` 增加导入：

```python
import shutil
from fastapi import File, Form, UploadFile
```

- [ ] 增加 Pydantic 请求模型：

```python
class DatabaseRegisterRequest(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = ""


class DatabaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
```

- [ ] 增加 `_database_payload(item)`，统一返回：
  - `id`
  - `name`
  - `description`
  - `status`
  - `engine`
  - `documents`
  - `working_dir`
  - `output_dir`
  - `updated_at`
- [ ] 实现 `/db/register`。
- [ ] 实现 `/db/{db_id}`。
- [ ] 实现 `/db/{db_id}/documents`。
- [ ] 实现 `/ingest/upload`：
  - 保存到 `rag-anything-api\storage\files\{database}\{filename}`
  - 再调用 `service.ingest_file(db_id, target)`
  - 出错时返回 500 和错误详情
- [ ] 更新 `/db/list`，返回 `description` 和 `documents` 数量。
- [ ] 运行完整 RAG 测试：

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python -m pytest tests -v
```

- [ ] 提交：

```powershell
git add rag-anything-api\app.py rag-anything-api\database_registry.py rag-anything-api\tests\test_database_management_api.py
git commit -m "feat: add rag knowledge management api"
```

---

## 任务 3：建立统一工作台壳

**文件：**

- 修改：`ai-tutor-system\static\index.html`
- 修改：`ai-tutor-system\static\css\style.css`
- 新建：`ai-tutor-system\static\js\api.js`
- 新建：`ai-tutor-system\static\js\navigation.js`
- 新建：`ai-tutor-system\static\js\health.js`

### 页面结构

统一入口使用左侧导航 + 顶部状态 + 页面内容区：

- 总览
- 知识库
- 内容生成
- 陪练系统
- 历史产物

### 步骤

- [ ] 先记录当前陪练页面用到的 ID，避免后面迁移时漏掉：

```powershell
cd D:\GitHub_WorkSpace\Test-System
rg -n "id=\"|class=\"|script src" ai-tutor-system\static\index.html
```

- [ ] 新建 `api.js`：
  - `CONFIG.RAG_API = "http://localhost:8003"`
  - `CONFIG.TUTOR_API = "http://localhost:8002"`
  - `requestJson(url, options)`
  - `postJson(url, payload)`
  - `putJson(url, payload)`
- [ ] 新建 `navigation.js`：
  - `showWorkbenchPage(pageId)`
  - `initNavigation()`
  - 根据 `data-nav` 和 `data-page` 切换页面
- [ ] 新建 `health.js`：
  - 请求 `http://localhost:8003/health`
  - 请求 `http://localhost:8002/api/status`
  - 渲染服务状态标签
- [ ] 改造 `index.html`：
  - 删除旧的欢迎卡片式单页结构。
  - 增加 `.app-shell`。
  - 左侧 `.sidebar` 放导航。
  - 主区 `.main-shell` 放 `topbar` 和五个 `section[data-page]`。
  - 每个功能区先放容器：
    - `#knowledgeApp`
    - `#generationApp`
    - `#tutorApp`
    - `#historyApp`
- [ ] 改造 `style.css`：
  - 定义统一变量：背景、卡片、边框、文字、主色、状态色。
  - 实现 sidebar、topbar、metric-card、section-block。
  - 适配 900px 以下布局。
- [ ] 启动服务手工验证：

```powershell
cd D:\GitHub_WorkSpace\Test-System\ai-tutor-system
python tutor_backend.py
```

打开 `http://localhost:8002`。

验收：

- [ ] 左侧导航可见。
- [ ] 点击导航能切换页面。
- [ ] 顶部能显示 RAG 服务和陪练服务状态。
- [ ] 390px 宽度下不重叠。

- [ ] 提交：

```powershell
git add ai-tutor-system\static\index.html ai-tutor-system\static\css\style.css ai-tutor-system\static\js\api.js ai-tutor-system\static\js\navigation.js ai-tutor-system\static\js\health.js
git commit -m "feat: add unified workbench shell"
```

---

## 任务 4：实现知识库管理页面

**文件：**

- 新建：`ai-tutor-system\static\js\knowledge.js`
- 修改：`ai-tutor-system\static\index.html`
- 修改：`ai-tutor-system\static\css\style.css`

### 功能目标

知识库页面要支持：

- 查看所有知识库。
- 创建知识库。
- 选择当前知识库。
- 上传文件并导入。
- 查看当前知识库已导入文件。
- 总览页同步显示知识库数量和文件数量。

### 步骤

- [ ] 新建 `knowledge.js`，维护状态：

```javascript
const knowledgeState = {
  databases: [],
  activeDatabase: "",
};
```

- [ ] 实现 `loadKnowledgeBases()`：
  - 请求 `GET ${CONFIG.RAG_API}/db/list`
  - 更新 `knowledgeState.databases`
  - 默认选中第一个知识库
  - 调用 `renderKnowledgePage()`
  - 调用 `loadKnowledgeDocuments()`
- [ ] 实现 `renderKnowledgePage()`：
  - 左侧卡片：创建知识库表单
  - 右侧卡片：知识库列表
  - 下方卡片：上传文件和文件列表
- [ ] 实现 `createKnowledgeBase()`：
  - 请求 `POST /db/register`
  - 创建成功后刷新列表
- [ ] 实现 `uploadKnowledgeFile()`：
  - 使用 `FormData`
  - 字段：`database`、`file`
  - 请求 `POST /ingest/upload`
  - 上传时显示“正在上传并导入，RAG-Anything 解析可能需要较长时间...”
- [ ] 实现 `loadKnowledgeDocuments()`：
  - 请求 `GET /db/{database}/documents`
  - 渲染文件名、状态、来源
- [ ] 在 `index.html` 加载：

```html
<script src="/static/js/knowledge.js"></script>
```

- [ ] 初始化时调用：

```javascript
loadKnowledgeBases().catch((error) => console.error(error));
```

- [ ] 增加 CSS：
  - `.content-grid`
  - `.panel-card`
  - `.panel-pad`
  - `.db-item`
  - `.upload-row`
  - `.file-row`
  - `.empty-state`
  - `.status-text`
- [ ] 手工验证：
  - 打开 `http://localhost:8002`
  - 进入“知识库”
  - 能看到 `商务彩铃`
  - 能创建测试知识库
  - 能上传小 `.txt` 文件
  - 上传后文件列表刷新
- [ ] 提交：

```powershell
git add ai-tutor-system\static\index.html ai-tutor-system\static\css\style.css ai-tutor-system\static\js\knowledge.js
git commit -m "feat: add knowledge management page"
```

---

## 任务 5：增加内容生成 API

**文件：**

- 新建：`ai-tutor-system\generation_runner.py`
- 新建：`ai-tutor-system\generation_api.py`
- 修改：`ai-tutor-system\tutor_backend.py`
- 新建测试：`ai-tutor-system\tests\test_generation_api.py`

### API 目标

- `POST /generation/jobs`
  - 创建生成任务。
- `GET /generation/jobs/{job_id}`
  - 查询任务结果。
- `GET /generation/artifacts`
  - 查看历史产物。
- `GET /generation/artifacts/download?path=...`
  - 下载产物。

### 步骤

- [ ] 写测试：创建生成任务。
- [ ] 写测试：查询生成任务。
- [ ] 写测试：查看产物列表。
- [ ] 新建 `generation_runner.py`：
  - 生成 `job_id`
  - 保存任务 JSON 到 `ai-tutor-system\tutor_data\generation_jobs`
  - 调用根目录 `run_skill_compliance_suite.py`
  - 收集 `solution_file` 和 `training_files`
  - 扫描 `solution_output` 和 `training_output` 中的 `.md` 文件
- [ ] 新建 `generation_api.py`：
  - 定义 `GenerationRequest`
  - 挂载 router 前缀 `/generation`
  - 增加任务创建、任务查询、产物列表、下载接口
  - 下载接口必须限制路径只能在 `training_output` 和 `solution_output`
- [ ] 修改 `tutor_backend.py`：

```python
from generation_api import router as generation_router

app.include_router(generation_router)
```

- [ ] 运行测试：

```powershell
cd D:\GitHub_WorkSpace\Test-System\ai-tutor-system
python -m pytest tests\test_generation_api.py -v
```

- [ ] 提交：

```powershell
git add ai-tutor-system\generation_api.py ai-tutor-system\generation_runner.py ai-tutor-system\tutor_backend.py ai-tutor-system\tests\test_generation_api.py
git commit -m "feat: add generation api"
```

---

## 任务 6：实现内容生成页面和历史产物

**文件：**

- 新建：`ai-tutor-system\static\js\generation.js`
- 修改：`ai-tutor-system\static\index.html`
- 修改：`ai-tutor-system\static\css\style.css`

### 功能目标

页面支持：

- 选择知识库。
- 输入客户单位、汇报对象、客情关系、目标受众、培训时长、题量。
- 一键生成方案、讲义、测试题、README。
- 查看并下载历史 Markdown 产物。

### 步骤

- [ ] 新建 `generation.js`。
- [ ] 实现 `renderGenerationPage()`：
  - 左侧表单：生成参数。
  - 右侧列表：生成结果。
- [ ] 实现 `hydrateGenerationDatabases()`：
  - 从 `knowledgeState.databases` 填充知识库下拉框。
- [ ] 实现 `startGenerationJob()`：
  - 请求 `POST ${CONFIG.TUTOR_API}/generation/jobs`
  - 显示“正在生成材料，通常需要数分钟...”
  - 完成后刷新历史产物
- [ ] 实现 `loadGenerationArtifacts()`：
  - 请求 `GET /generation/artifacts`
  - 渲染文件名、类型、下载链接
  - 同步填充 `#historyApp`
- [ ] 在 `index.html` 加载 `generation.js`。
- [ ] 在知识库加载完成后调用 `renderGenerationPage()`。
- [ ] 增加 `.download-link` 等少量 CSS。
- [ ] 手工验证：
  - 进入“内容生成”
  - 能选择知识库
  - 点击生成后能看到状态
  - 生成成功后历史产物可下载
- [ ] 提交：

```powershell
git add ai-tutor-system\static\index.html ai-tutor-system\static\css\style.css ai-tutor-system\static\js\generation.js
git commit -m "feat: add content generation page"
```

---

## 任务 7：改造陪练系统界面并支持选择知识库

**文件：**

- 新建：`ai-tutor-system\static\js\tutor.js`
- 修改：`ai-tutor-system\static\index.html`
- 修改：`ai-tutor-system\static\css\style.css`
- 修改：`ai-tutor-system\tutor_backend.py`
- 修改：`ai-tutor-system\tutor_config.py`

### 后端目标

陪练会话启动时可以显式传入 `database`。如果前端不传，继续使用原有产品名映射/默认知识库。

### 步骤

- [ ] 修改 `SessionStart`：

```python
class SessionStart(BaseModel):
    scenario_id: str
    client_unit: str
    product: str
    scenario_type: Optional[str] = "初次沟通"
    database: Optional[str] = None
    custom_scenario: Optional[ScenarioCreate] = None
```

- [ ] `start_session()` 保存：

```python
"database": session_start.database,
```

- [ ] `chat()` 中优先使用：

```python
database = session_data.get("database") or resolve_product_database(product)
```

- [ ] 报告生成、暂停反馈等路径也使用相同逻辑。
- [ ] 新建 `tutor.js`：
  - 渲染开始页、聊天页、报告页到 `#tutorApp`
  - 保留原有关键 ID：`scenarioSelect`、`clientUnit`、`productName`、`scenarioType`、`startBtn`、`chatMessages`、`messageInput`、`sendBtn`、`pauseBtn`、`endBtn`
  - 增加 `tutorDatabase` 下拉框
- [ ] 从旧 `app_with_health_check.js` 迁移陪练逻辑到 `tutor.js`：
  - `startSession`
  - `sendMessage`
  - `endSession`
  - `getHistory`
  - `addMessage`
  - `updateInfoPanel`
  - `updateLiveSuggestions`
  - `updateKnowledgeBox`
- [ ] `startSession()` 请求体增加：

```javascript
database: document.getElementById("tutorDatabase").value
```

- [ ] 增加陪练 CSS：
  - `.tutor-chat-grid`
  - `.chat-card`
  - `.chat-toolbar`
  - `.chat-messages`
  - `.chat-input-area`
  - `.info-list`
  - `.suggestion-box`
- [ ] 手工验证：
  - 能选择知识库
  - 能开始陪练
  - 能发送消息
  - 能看到知识库检索状态
  - 能结束并看到报告
- [ ] 提交：

```powershell
git add ai-tutor-system\tutor_backend.py ai-tutor-system\tutor_config.py ai-tutor-system\static\index.html ai-tutor-system\static\css\style.css ai-tutor-system\static\js\tutor.js
git commit -m "feat: restyle tutor in unified workbench"
```

---

## 任务 8：文档和最终验证

**文件：**

- 修改：`使用说明.md`
- 修改：`未来优化方向.md`

### 步骤

- [ ] 更新 `使用说明.md`，新增“统一工作台”章节：

```markdown
## 统一工作台

启动 `rag-anything-api` 和 `ai-tutor-system` 后，访问：

- 工作台：http://localhost:8002
- RAG API 文档：http://localhost:8003/docs
- 陪练/生成 API 文档：http://localhost:8002/docs

工作台包含：

1. 总览：查看服务状态、知识库数量、文件数量和最近产物。
2. 知识库：创建产品知识库，上传文件并导入 RAG-Anything。
3. 内容生成：选择知识库后生成解决方案、培训讲义、测试题和 README。
4. 陪练系统：选择知识库、客户场景和产品后开始对话陪练。
5. 历史产物：查看并下载生成的 Markdown 文件。
```

- [ ] 更新 `未来优化方向.md`：
  - 已完成：统一工作台、网页端知识库管理、网页端内容生成、陪练选择知识库。
  - 后续优化：后台队列、进度条、认证审计、产品到知识库映射管理。
- [ ] 运行 RAG 后端测试：

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python -m pytest tests -v
```

- [ ] 运行陪练/生成测试：

```powershell
cd D:\GitHub_WorkSpace\Test-System\ai-tutor-system
python -m pytest tests -v
```

- [ ] 启动服务：

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python app.py
```

另一个终端：

```powershell
cd D:\GitHub_WorkSpace\Test-System\ai-tutor-system
python tutor_backend.py
```

- [ ] 手工端到端验收：
  - 打开 `http://localhost:8002`
  - 服务状态正常
  - 创建 `联调测试库`
  - 上传一个小 `.txt` 文件
  - 用该库生成材料
  - 下载一个 Markdown 产物
  - 用该库开始一次陪练
  - 发送一条消息
  - 结束会话并看到报告
- [ ] 响应式检查：
  - 1366px 桌面
  - 900px 平板边界
  - 390px 手机宽度
  - 验收：无文字重叠、按钮不溢出、陪练输入区可见
- [ ] 提交文档：

```powershell
git add 使用说明.md 未来优化方向.md
git commit -m "docs: document unified workbench"
```

---

## 三、关键风险

- **RAG-Anything 导入慢。** 第一版先用同步上传并明确 loading 文案；后续再做后台队列和进度条。
- **生成任务耗时长。** 第一版沿用现有 `run_skill_compliance_suite.py`，后续再拆成可选择的单项生成。
- **旧前端 JS 耦合较重。** 陪练逻辑从 `app_with_health_check.js` 拆到 `tutor.js`，健康检查拆到 `health.js`。
- **产品和知识库映射还不完善。** 第一版先让用户显式选择知识库，后续再做“产品-知识库”映射管理页面。

---

## 四、自检结果

- 覆盖了你提出的五点需求：
  - 陪练系统改造：任务 7。
  - 生成试卷、讲义、解决方案上网页端：任务 5、6。
  - RAG-Anything 后知识库区分：任务 1、2、4、7。
  - 添加文件的前端界面：任务 2、4。
  - 启动页/页面关联：任务 3、6、8。
- 没有留“以后再说”的空任务；每个任务都有文件、步骤、测试或手工验收。
- 代码标识和命令保留英文，说明文字已改为中文，方便明天直接执行。
