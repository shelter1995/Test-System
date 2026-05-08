# RAGAnything Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化 Test-System 的 RAG-Anything 知识库服务，降低实时陪练延迟，提高多库查询稳定性，清理生命周期与文档债务，同时保持现有 HTTP API 兼容。

**Architecture:** 保留 `rag-anything-api` 作为唯一知识库服务入口，继续监听 `http://localhost:8003` 并兼容现有 `/search`、`/ai_enhanced_search`、`/query`、`/ingest/*`、`/db/*` 接口。优化集中在服务生命周期、查询并发、轻量上下文接口、RAG 实例缓存和文档一致性五个方面，所有运行路径继续通过 `RAGAnythingService`，不重新引入旧 LightRAG/Chroma/FAISS 直连栈。

**Tech Stack:** FastAPI lifespan, asyncio, HKUDS/RAG-Anything, MinerU, LightRAG, pytest, FastAPI TestClient, PowerShell.

---

## Current Facts

- 主服务入口：`D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
- 服务封装：`D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
- 注册表：`D:\GitHub_WorkSpace\Test-System\rag-anything-api\database_registry.py`
- 现有测试目录：`D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests`
- 陪练系统调用：`D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tutor_backend.py`
- 技能流水线调用：`D:\GitHub_WorkSpace\Test-System\run_skill_compliance_suite.py`
- 已有边界测试：`rag-anything-api/tests/test_migration_boundaries.py` 防止运行路径重新引入旧直连栈
- 当前测试命令：`python -m pytest rag-anything-api/tests -q`

---

## File Structure

### Modify

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
  - 用 lifespan 替换 `@app.on_event("startup")`
  - 增加轻量上下文接口 `/context`
  - 保持旧接口响应合同不变

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
  - `query_all()` 改为并发执行
  - 增加单库查询超时参数
  - 增加 `query_context()` 轻量上下文方法
  - 给 `_instances` 增加 LRU 上限和 unload 能力

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
  - 增加 `QUERY_ALL_TIMEOUT`
  - 增加 `MAX_RAG_INSTANCES`
  - 增加 `CONTEXT_QUERY_MODE`
  - 增加 `CONTEXT_MAX_CHARS`

- `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tutor_backend.py`
  - 陪练实时检索优先调用 `/context`
  - `/context` 不可用时自动回退 `/ai_enhanced_search`

- `D:\GitHub_WorkSpace\Test-System\rag_database_guide.md`
  - 清理旧 Chroma、旧 `storage/lightrag/{database}`、旧处理器说明
  - 明确当前入库、查询、备份路径

- `D:\GitHub_WorkSpace\Test-System\使用说明.md`
  - 增加 `/context` 用法
  - 更新 RAG-Anything 运行栈说明

- `D:\GitHub_WorkSpace\Test-System\未来优化方向.md`
  - 把本计划完成的事项移到“已完成”或删除重复建议

### Test

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_app_lifespan.py`
- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_query_all_concurrency.py`
- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_context_contract.py`
- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_instance_cache.py`
- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_docs_no_legacy_rag_paths.py`

---

## Task 1: Replace FastAPI Startup Event With Lifespan

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_app_lifespan.py`

- [ ] **Step 1: Write failing lifespan startup test**

Create `rag-anything-api/tests/test_app_lifespan.py`:

```python
from fastapi.testclient import TestClient

import app as rag_api


class FakeRegistry:
    def __init__(self, registry_file):
        self.registry_file = registry_file
        self.seeded = []

    def list_databases(self):
        return [{"id": "商务彩铃", "name": "商务彩铃", "status": "active", "documents": []}]

    def get_database(self, db_id):
        return {"id": db_id, "name": db_id, "status": "active", "documents": []}

    def register_database(self, database_id, name=None, working_dir=None, output_dir=None):
        item = {
            "id": database_id,
            "name": name or database_id,
            "status": "active",
            "documents": [],
            "working_dir": working_dir or "",
            "output_dir": output_dir or "",
        }
        self.seeded.append(item)
        return item


class FakeService:
    def __init__(self, storage_root, output_root, registry):
        self.storage_root = storage_root
        self.output_root = output_root
        self.registry = registry


def test_lifespan_initializes_registry_and_service(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_api.config, "DATABASE_REGISTRY_FILE", tmp_path / "databases.json")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path / "raganything")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(rag_api.config, "DEFAULT_DATABASE_IDS", ["商务彩铃"])
    monkeypatch.setattr(rag_api, "DatabaseRegistry", FakeRegistry)
    monkeypatch.setattr(rag_api, "RAGAnythingService", FakeService)

    rag_api.rag_service = None
    rag_api.registry = None
    rag_api.startup_error = "previous error"

    with TestClient(rag_api.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["engine"] == "ready"
    assert rag_api.startup_error is None
    assert isinstance(rag_api.rag_service, FakeService)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_app_lifespan.py::test_lifespan_initializes_registry_and_service -q
```

Expected: FAIL because `app.py` still uses `@app.on_event("startup")` and the TestClient lifespan path has not been explicitly defined.

- [ ] **Step 3: Implement lifespan helper and remove startup decorator**

In `rag-anything-api/app.py`, add import:

```python
from contextlib import asynccontextmanager
```

Replace the decorated startup function:

```python
@app.on_event("startup")
async def startup_event():
    global rag_service, registry, startup_error
    try:
        registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
        _ensure_registry_seeded()
        rag_service = RAGAnythingService(
            storage_root=config.RAGANYTHING_STORAGE_ROOT,
            output_root=config.RAGANYTHING_OUTPUT_ROOT,
            registry=registry,
        )
        startup_error = None
        logger.info("RAG-Anything 服务初始化完成")
    except Exception as e:
        rag_service = None
        startup_error = str(e)
        logger.error(f"RAG-Anything 服务初始化失败: {e}")
```

With:

```python
async def initialize_service() -> None:
    global rag_service, registry, startup_error
    try:
        registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
        _ensure_registry_seeded()
        rag_service = RAGAnythingService(
            storage_root=config.RAGANYTHING_STORAGE_ROOT,
            output_root=config.RAGANYTHING_OUTPUT_ROOT,
            registry=registry,
        )
        startup_error = None
        logger.info("RAG-Anything 服务初始化完成")
    except Exception as e:
        rag_service = None
        startup_error = str(e)
        logger.error(f"RAG-Anything 服务初始化失败: {e}")


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await initialize_service()
    yield
```

Move `app = FastAPI(...)` below `lifespan()` or pass `lifespan=lifespan` when creating the app:

```python
app = FastAPI(
    title="RAG-Anything 智能检索系统",
    description="基于 HKUDS/RAG-Anything 的增强检索服务",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
)
```

- [ ] **Step 4: Run focused test and warning check**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_app_lifespan.py -q
python -m pytest rag-anything-api/tests -q
```

Expected: PASS and no FastAPI `on_event is deprecated` warning.

---

## Task 2: Make Multi-Database Query Concurrent With Per-Database Timeout

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_query_all_concurrency.py`

- [ ] **Step 1: Write failing concurrency test**

Create `rag-anything-api/tests/test_query_all_concurrency.py`:

```python
import asyncio
import time
from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        await asyncio.sleep(0.1)
        return f"{question}:{mode}"


def test_query_all_runs_databases_concurrently(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("库A")
    registry.register_database("库B")
    registry.register_database("库C")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: FakeRAG(),
        query_timeout=1.0,
    )

    start = time.perf_counter()
    result = asyncio.run(service.query_all("资费", mode="naive", n_results=3))
    elapsed = time.perf_counter() - start

    assert result["total_found"] == 3
    assert elapsed < 0.2
```

- [ ] **Step 2: Write failing timeout isolation test**

Append to `test_query_all_concurrency.py`:

```python
class SlowRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        await asyncio.sleep(0.2)
        return "slow"


class FastRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        return "fast"


def test_query_all_keeps_fast_results_when_one_database_times_out(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("慢库")
    registry.register_database("快库")

    def factory(db_id, _wd):
        return SlowRAG() if db_id == "慢库" else FastRAG()

    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=factory,
        query_timeout=0.05,
    )

    result = asyncio.run(service.query_all("资费", mode="naive", n_results=5))

    assert result["total_found"] == 1
    assert result["results"][0]["text"] == "fast"
    assert result["errors"][0]["database"] == "慢库"
    assert "timeout" in result["errors"][0]["error"].lower()
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_query_all_concurrency.py -q
```

Expected: FAIL because current `query_all()` runs sequentially and has no `errors` field.

- [ ] **Step 4: Add config values**

In `rag-anything-api/config.py`, add near timeout settings:

```python
QUERY_ALL_TIMEOUT = _safe_int(os.getenv("QUERY_ALL_TIMEOUT", "60"), 60)
```

- [ ] **Step 5: Update service constructor**

In `raganything_service.py`, extend `RAGAnythingService.__init__`:

```python
def __init__(
    self,
    storage_root: str | Path,
    output_root: str | Path,
    registry: DatabaseRegistry,
    rag_factory: Callable[[str, Path], Any] | None = None,
    query_timeout: float | None = None,
):
    self.storage_root = Path(storage_root)
    self.output_root = Path(output_root)
    self.registry = registry
    self.rag_factory = rag_factory or self._create_rag
    self.query_timeout = float(query_timeout or config.QUERY_ALL_TIMEOUT)
    self._instances: dict[str, Any] = {}
```

- [ ] **Step 6: Replace query_all with concurrent implementation**

Replace `query_all()` in `raganything_service.py`:

```python
async def query_all(self, query: str, mode: str = "hybrid", n_results: int = 10) -> dict[str, Any]:
    async def query_one(db_id: str):
        try:
            return await asyncio.wait_for(
                self.query(db_id, query, mode=mode, n_results=1),
                timeout=self.query_timeout,
            )
        except asyncio.TimeoutError:
            return {
                "database": db_id,
                "error": f"timeout after {self.query_timeout}s",
                "results": [],
            }
        except Exception as exc:
            return {
                "database": db_id,
                "error": str(exc),
                "results": [],
            }

    db_ids = [
        str(db.get("id", "")).strip()
        for db in self.registry.list_databases()
        if str(db.get("id", "")).strip()
    ]
    responses = await asyncio.gather(*(query_one(db_id) for db_id in db_ids))

    merged = []
    errors = []
    for response in responses:
        merged.extend(response.get("results", []))
        if response.get("error"):
            errors.append({"database": response.get("database"), "error": response.get("error")})

    return {
        "query": query,
        "results": merged[: max(1, n_results)],
        "total_found": len(merged),
        "errors": errors,
    }
```

Add import at top:

```python
import asyncio
```

- [ ] **Step 7: Run focused and full tests**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_query_all_concurrency.py -q
python -m pytest rag-anything-api/tests -q
```

Expected: PASS.

---

## Task 3: Add Lightweight Context Retrieval Path For Real-Time Coaching

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tutor_backend.py`
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_context_contract.py`

- [ ] **Step 1: Write failing service context test**

Create `rag-anything-api/tests/test_context_contract.py`:

```python
import asyncio
from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class ContextRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="naive", **kwargs):
        assert kwargs.get("only_need_context") is True
        return "第一段知识\n第二段知识\n第三段知识"


def test_query_context_returns_trimmed_context_payload(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: ContextRAG(),
    )

    result = asyncio.run(service.query_context("商务彩铃", "资费", mode="naive", max_chars=8))

    assert result == {
        "query": "资费",
        "database": "商务彩铃",
        "contexts": [
            {
                "text": "第一段知识",
                "metadata": {"source": "raganything", "database": "商务彩铃", "mode": "naive"},
                "score": 1.0,
            }
        ],
        "total_found": 1,
    }
```

- [ ] **Step 2: Write failing API contract test**

Append:

```python
from fastapi.testclient import TestClient
import app as rag_api


class FakeContextService:
    async def query_context(self, database_id, query, mode="naive", max_chars=2000):
        return {
            "query": query,
            "database": database_id,
            "contexts": [
                {
                    "text": "商务彩铃上下文",
                    "metadata": {"source": "raganything", "database": database_id, "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }


def test_context_endpoint_contract(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FakeContextService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.post("/context", json={"query": "资费", "database": "商务彩铃", "n_results": 3})

    assert response.status_code == 200
    assert response.json()["contexts"][0]["text"] == "商务彩铃上下文"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_context_contract.py -q
```

Expected: FAIL because `query_context()` and `/context` do not exist.

- [ ] **Step 4: Add config values**

In `config.py`:

```python
CONTEXT_QUERY_MODE = os.getenv("CONTEXT_QUERY_MODE", "naive").strip().lower() or "naive"
CONTEXT_MAX_CHARS = _safe_int(os.getenv("CONTEXT_MAX_CHARS", "3000"), 3000)
```

- [ ] **Step 5: Implement service method**

In `raganything_service.py`, add:

```python
async def query_context(self, database_id: str, query: str, mode: str = "naive", max_chars: int = 3000) -> dict[str, Any]:
    rag = self.get_rag(database_id, create_if_missing=False)
    init_result = await rag._ensure_lightrag_initialized()
    if not init_result or not init_result.get("success"):
        raise RuntimeError(f"RAG 引擎初始化失败: {(init_result or {}).get('error', 'unknown')}")

    context = await rag.aquery(query, mode=mode, only_need_context=True)
    text = str(context).strip()
    if max_chars > 0:
        text = text[:max_chars]

    contexts = []
    if text:
        contexts.append(
            {
                "text": text,
                "metadata": {"source": "raganything", "database": database_id, "mode": mode},
                "score": 1.0,
            }
        )

    return {
        "query": query,
        "database": database_id,
        "contexts": contexts,
        "total_found": len(contexts),
    }
```

- [ ] **Step 6: Add API endpoint**

In `app.py`, add near `/query`:

```python
@app.post("/context")
async def context(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        if not db_id:
            raise HTTPException(status_code=400, detail="database 不能为空")
        return await service.query_context(
            db_id,
            request.query,
            mode=config.CONTEXT_QUERY_MODE,
            max_chars=config.CONTEXT_MAX_CHARS,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上下文检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 7: Update tutor retrieval with fallback**

In `ai-tutor-system/tutor_backend.py`, replace the request in `search_rag_knowledge()` with:

```python
endpoint = "context" if database else "ai_enhanced_search"
response = requests.post(
    f"{config.RAG_SERVICE_URL}/{endpoint}",
    json=params,
    timeout=config.RAG_REQUEST_TIMEOUT
)
if response.status_code == 404 and endpoint == "context":
    response = requests.post(
        f"{config.RAG_SERVICE_URL}/ai_enhanced_search",
        json=params,
        timeout=config.RAG_REQUEST_TIMEOUT
    )
```

Then parse both response shapes:

```python
data = response.json()
results = data.get("contexts", data.get("results", []))
```

- [ ] **Step 8: Run tests**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_context_contract.py -q
python -m pytest rag-anything-api/tests -q
python -m py_compile ai-tutor-system/tutor_backend.py
```

Expected: PASS.

---

## Task 4: Add RAG Instance Cache Limit And Explicit Unload

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_instance_cache.py`

- [ ] **Step 1: Write failing LRU eviction test**

Create `rag-anything-api/tests/test_instance_cache.py`:

```python
from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    def __init__(self, name):
        self.name = name


def test_get_rag_evicts_least_recently_used_instance(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    for db_id in ["A", "B", "C"]:
        registry.register_database(db_id)

    created = []

    def factory(db_id, _wd):
        rag = FakeRAG(db_id)
        created.append(rag)
        return rag

    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=factory,
        max_instances=2,
    )

    service.get_rag("A")
    service.get_rag("B")
    service.get_rag("A")
    service.get_rag("C")

    assert list(service._instances.keys()) == ["A", "C"]
    assert [rag.name for rag in created] == ["A", "B", "C"]
```

- [ ] **Step 2: Write failing unload test**

Append:

```python
def test_unload_rag_removes_cached_instance(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda db_id, _wd: FakeRAG(db_id),
        max_instances=2,
    )

    service.get_rag("商务彩铃")
    removed = service.unload_rag("商务彩铃")

    assert removed is True
    assert "商务彩铃" not in service._instances
    assert service.unload_rag("商务彩铃") is False
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_instance_cache.py -q
```

Expected: FAIL because constructor has no `max_instances` and no `unload_rag()`.

- [ ] **Step 4: Add config**

In `config.py`:

```python
MAX_RAG_INSTANCES = _safe_int(os.getenv("MAX_RAG_INSTANCES", "3"), 3)
```

- [ ] **Step 5: Implement OrderedDict cache**

In `raganything_service.py`, add import:

```python
from collections import OrderedDict
```

Update constructor:

```python
max_instances: int | None = None,
```

Set fields:

```python
self.max_instances = max(1, int(max_instances or config.MAX_RAG_INSTANCES))
self._instances: OrderedDict[str, Any] = OrderedDict()
```

In `get_rag()`, before returning cached item:

```python
if database_id in self._instances:
    self._instances.move_to_end(database_id)
    return self._instances[database_id]
```

After creating a new instance:

```python
self._instances[database_id] = self.rag_factory(database_id, working_dir)
self._instances.move_to_end(database_id)
while len(self._instances) > self.max_instances:
    self._instances.popitem(last=False)
```

Add method:

```python
def unload_rag(self, database_id: str) -> bool:
    database_id = str(database_id).strip()
    if database_id not in self._instances:
        return False
    self._instances.pop(database_id, None)
    return True
```

- [ ] **Step 6: Run tests**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_instance_cache.py -q
python -m pytest rag-anything-api/tests -q
```

Expected: PASS.

---

## Task 5: Clean Legacy RAG Documentation And Guard Against Regression

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag_database_guide.md`
- Modify: `D:\GitHub_WorkSpace\Test-System\使用说明.md`
- Modify: `D:\GitHub_WorkSpace\Test-System\未来优化方向.md`
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_docs_no_legacy_rag_paths.py`

- [ ] **Step 1: Write failing docs regression test**

Create `rag-anything-api/tests/test_docs_no_legacy_rag_paths.py`:

```python
from pathlib import Path


def test_user_facing_docs_do_not_recommend_legacy_rag_storage_or_endpoints():
    root = Path(__file__).resolve().parents[2]
    docs = [
        root / "rag_database_guide.md",
        root / "使用说明.md",
        root / "未来优化方向.md",
    ]
    forbidden = [
        "chroma.sqlite3",
        "chromadb",
        "Chroma",
        "storage\\\\lightrag\\\\{数据库ID}",
        "storage/lightrag/{数据库ID}",
        "/ingest/file",
        "/ingest/folder",
        "旧图片处理器",
        "旧向量库",
    ]
    offenders = []
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in text:
                offenders.append(f"{doc.name}: {pattern}")

    assert offenders == []
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_docs_no_legacy_rag_paths.py -q
```

Expected: FAIL if user-facing docs still mention old storage or endpoints.

- [ ] **Step 3: Rewrite `rag_database_guide.md` around current stack**

Replace legacy sections with this structure:

```markdown
# RAG-Anything 知识库管理指南

## 当前统一入口

当前项目知识库服务统一使用 `http://localhost:8003`，底层为 `RAGAnything + MinerU + LightRAG`。

常用接口：

- `GET /db/list`
- `GET /db/stats`
- `GET /db/stats/{database}`
- `POST /search`
- `POST /ai_enhanced_search`
- `POST /context`
- `POST /ingest/path`
- `POST /ingest/text`

## 存储目录

知识库注册表：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\databases.json
```

RAG-Anything 主存储：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\raganything\{database}\rag_storage
```

解析输出：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\output\{database}
```

## 导入文件

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/ingest/path" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    path = "D:\GitHub_WorkSpace\Test-System\商务彩铃"
    database = "商务彩铃"
    recursive = $true
  } | ConvertTo-Json -Compress)
```

## 导入文本

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/ingest/text" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    text = "商务彩铃产品说明"
    database = "商务彩铃"
    source = "manual"
  } | ConvertTo-Json -Compress)
```

## 查询

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/search" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    query = "商务视频彩铃资费是多少"
    database = "商务彩铃"
    n_results = 5
  } | ConvertTo-Json -Compress)
```

## 轻量上下文查询

实时陪练优先使用 `/context`，用于获取知识上下文而不是完整生成答案。

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8003/context" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    query = "价格异议处理"
    database = "商务彩铃"
    n_results = 5
  } | ConvertTo-Json -Compress)
```
```

- [ ] **Step 4: Update `使用说明.md`**

Ensure the architecture section says:

```markdown
系统包含两个核心服务：

1. **RAG-Anything 知识库服务**：端口 8003，负责文档解析、知识图谱、向量检索和兼容 REST API。
2. **AI 话术陪练系统**：端口 8002，负责场景会话、MiniMax 对话生成、实时评估和报告。
```

Ensure RAG section includes `/context`:

```markdown
#### 轻量上下文检索

- **端点**: `/context`
- **方法**: `POST`
- **用途**: 实时陪练优先使用，返回知识上下文，避免每次检索都生成完整答案。
```

- [ ] **Step 5: Update `未来优化方向.md`**

Move completed items into a completed section:

```markdown
## 已完成

- 主运行链路已统一到 RAG-Anything 服务层。
- 迁移导入脚本已统一复用 `RAGAnythingService`。
- 可执行 Python 路径已清理旧 LightRAG/Chroma/FAISS 直连栈。

## 后续优化

- 观察 `/context` 在实时陪练中的响应时间。
- 根据数据库数量调整 `MAX_RAG_INSTANCES` 和 `QUERY_ALL_TIMEOUT`。
- 如果 MinerU 入库耗时过高，再引入后台任务队列。
```

- [ ] **Step 6: Run docs test and full tests**

Run:

```powershell
python -m pytest rag-anything-api/tests/test_docs_no_legacy_rag_paths.py -q
python -m pytest rag-anything-api/tests -q
```

Expected: PASS.

---

## Final Verification

- [ ] Run all RAG API tests:

```powershell
python -m pytest rag-anything-api/tests -q
```

Expected: all tests pass.

- [ ] Compile touched Python files:

```powershell
python -m py_compile `
  rag-anything-api/app.py `
  rag-anything-api/config.py `
  rag-anything-api/raganything_service.py `
  ai-tutor-system/tutor_backend.py
```

Expected: no output and exit code 0.

- [ ] Scan runtime Python paths for legacy direct RAG stacks:

```powershell
Select-String -Path (Get-ChildItem -Recurse -File -Include *.py | Where-Object { $_.FullName -notmatch '\\.venv\\|__pycache__|\\.pytest_cache\\|\\tests\\' } | Select-Object -ExpandProperty FullName) -Pattern 'from lightrag import LightRAG|LightRAG\(|\.ainsert\(|from sentence_transformers|chromadb|Chroma|FAISS' -CaseSensitive:$false
```

Expected: no output.

- [ ] If local service is running, verify status and contract:

```powershell
Invoke-RestMethod -Uri "http://localhost:8003/status" -Method Get
Invoke-RestMethod `
  -Uri "http://localhost:8003/context" `
  -Method Post `
  -ContentType "application/json" `
  -Body (@{
    query = "商务视频彩铃资费是多少"
    database = "商务彩铃"
    n_results = 3
  } | ConvertTo-Json -Compress)
```

Expected: `/status` reports `engine_stack = RAGAnything + MinerU + LightRAG`; `/context` returns `contexts`.

---

## Rollout Order

1. Task 1 first, because it removes the current framework warning without changing behavior.
2. Task 2 second, because it improves multi-database behavior behind existing APIs.
3. Task 3 third, because it adds a new optional fast path and then lets the tutor system adopt it with fallback.
4. Task 4 fourth, because cache behavior is internal and should land after query behavior is stable.
5. Task 5 last, because docs should reflect implemented behavior.

---

## Self-Review

Spec coverage:

- FastAPI lifespan warning: Task 1.
- Multi-database query performance: Task 2.
- Lightweight context path for real-time coaching: Task 3.
- RAG instance memory/cache control: Task 4.
- Legacy docs cleanup: Task 5.

Placeholder scan:

- No placeholder markers remain in actionable plan steps.
- Every code change task includes concrete test code, command, expected failure, implementation, and verification.

Type consistency:

- `RAGAnythingService.query_context(database_id, query, mode, max_chars)` is used consistently by service tests and `/context`.
- `RAGAnythingService(..., query_timeout=..., max_instances=...)` is introduced before tests depend on those constructor arguments passing.
- `/context` returns `contexts`; tutor fallback parses `contexts` first, then `results`.
