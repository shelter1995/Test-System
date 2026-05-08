# RAGAnything Engine Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Test-System 的 8003 知识库服务从手写 LightRAG 兼容层切换为 HKUDS/RAG-Anything 官方 `raganything.RAGAnything` 技术栈，同时保持陪练系统、解决方案生成、培训/考试出题现有 HTTP API 对接不变。

**Architecture:** 保留 `rag-anything-api` 作为 Test-System 内部统一知识库服务，继续监听 `http://localhost:8003`，继续提供 `/db/list`、`/search`、`/ai_enhanced_search`、`/query`、`/db/search` 等现有接口。替换内部引擎：从直接 `LightRAG` 改为 `RAGAnything + MinerU + LightRAG`，并用一个兼容层把 RAG-Anything 查询结果包装成原有业务需要的 JSON 结构。知识库按数据库 ID 分目录存储，动态注册到 `storage/databases.json`，导入文件时使用 RAG-Anything 官方 `process_document_complete()`。

**Tech Stack:** FastAPI, HKUDS/RAG-Anything (`raganything`), MinerU pipeline backend, LightRAG, MiniMax OpenAI-compatible LLM API, SiliconFlow `BAAI/bge-m3` embedding, pytest, requests.

---

## 0. 当前事实

### 已确认的本地资料

- RAG-Anything 本地项目：`D:\GitHub_WorkSpace\RAG-Anything`
- 参考部署文档：`D:\GitHub_WorkSpace\RAG-Anything\DEPLOY_GUIDE.md`
- 该项目已使用：
  - `from raganything import RAGAnything, RAGAnythingConfig`
  - `rag.process_document_complete(..., backend="pipeline")`
  - `rag.aquery(question, mode="hybrid")`
  - `.env` 中配置 MiniMax、SiliconFlow、MinerU、chunk 参数

### Test-System 当前状态

- 统一知识库服务目录：`D:\GitHub_WorkSpace\Test-System\rag-anything-api`
- 统一服务入口：`http://localhost:8003`
- 陪练系统调用：`ai-tutor-system/tutor_backend.py` 的 `search_rag_knowledge()` 调用 `/ai_enhanced_search`
- 方案编制调用：`solution-generator-skill/SKILL.md` 通过 HTTP 调用 `/search` 和 `/ai_enhanced_search`
- 培训/考试出题调用：`peixun-skill/SKILL.md` 通过 HTTP 调用 `/search`
- 当前问题：`rag-anything-api/app.py` 实际仍是直接 `from lightrag import LightRAG`，并没有使用 `raganything.RAGAnything`

### 兼容性目标

执行完成后，以下业务调用不需要改调用地址：

```text
GET  http://localhost:8003/db/list
GET  http://localhost:8003/db/stats/{database}
POST http://localhost:8003/search
POST http://localhost:8003/ai_enhanced_search
POST http://localhost:8003/query
POST http://localhost:8003/db/search
```

请求体继续兼容：

```json
{
  "query": "商务视频彩铃产品资费是多少",
  "n_results": 10,
  "database": "商务彩铃"
}
```

返回体继续兼容：

```json
{
  "query": "商务视频彩铃产品资费是多少",
  "results": [
    {
      "text": "回答内容",
      "metadata": {
        "source": "raganything",
        "database": "商务彩铃",
        "mode": "hybrid",
        "sources": ["1、 商务视频彩铃一页纸长图介绍.png"]
      },
      "score": 1.0
    }
  ],
  "total_found": 1
}
```

---

## 1. 文件结构设计

### 修改文件

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\requirements.txt`
  - 加入 `raganything` 或本地 editable 安装说明
  - 保留 FastAPI、uvicorn、python-dotenv、requests

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
  - 增加 RAG-Anything 官方配置项
  - 增加 `RAGANYTHING_SOURCE_DIR`
  - 增加 `RAGANYTHING_STORAGE_DIR`
  - 增加 `RAGANYTHING_OUTPUT_DIR`
  - 增加 parser、parse_method、backend、chunk、multimodal 开关
  - 保留动态数据库注册表函数

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\adapters.py`
  - 继续保留 MiniMax 与 SiliconFlow 函数，或新增 OpenAI-compatible 函数
  - 确保 embedding 函数显式传入 `max_token_size=5000`
  - 兼容 RAG-Anything 的 `llm_model_func` / `embedding_func`

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
  - 不再直接初始化 `LightRAG`
  - 改为初始化 `RAGAnythingService`
  - 保持所有现有路由路径和返回结构

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\start.py`
  - 依赖检查从 `lightrag` 改为 `raganything`、`mineru`
  - 保留启动 8003 行为

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\import_files.py`
  - 从手写读取 `txt/pdf/docx/pptx` 改为调用 `RAGAnything.process_document_complete()`
  - 支持图片、PDF、Office、Markdown、文本等官方支持格式
  - 保留 CLI 参数 `--database`、`--recursive`

- `D:\GitHub_WorkSpace\Test-System\ocr_failed_file.py`
  - 改为说明或包装官方 RAG-Anything/MinerU 图片解析，不再默认 easyocr 手工转换

- `D:\GitHub_WorkSpace\Test-System\部署说明.md`
  - 更新依赖安装、MinerU、LibreOffice、启动说明

- `D:\GitHub_WorkSpace\Test-System\rag_database_guide.md`
  - 更新新建知识库命令和支持格式

### 新增文件

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
  - RAG-Anything 官方引擎封装
  - 按数据库 ID 管理 `RAGAnything` 实例
  - 提供 `query()`、`ingest_file()`、`ingest_folder()`、`list_databases()`、`get_stats()`

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\database_registry.py`
  - 读写 `storage/databases.json`
  - 记录每个知识库的文档清单、导入时间、文件 hash、状态
  - 从 `config.py` 中拆出动态注册表职责

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_database_registry.py`
  - 测试注册表增删改查和去重

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_api_contract.py`
  - 测试 `/db/list`、`/search`、`/ai_enhanced_search` 的兼容 JSON 格式

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_raganything_service.py`
  - 用 fake RAGAnything 对象测试服务封装，不调用外部 API

### 保留但不作为新引擎使用

- `D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\lightrag`
  - 当前已有测试数据，执行前先备份
  - 新引擎使用 `storage/raganything`

---

## 2. 存储方案

### 目标结构

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage
├── databases.json
├── lightrag_backup_YYYYMMDD_HHMMSS
└── raganything
    └── 商务彩铃
        ├── rag_storage
        └── output
```

### `databases.json` 结构

```json
{
  "databases": [
    {
      "id": "商务彩铃",
      "name": "商务彩铃",
      "status": "active",
      "engine": "raganything",
      "working_dir": "storage/raganything/商务彩铃/rag_storage",
      "output_dir": "storage/raganything/商务彩铃/output",
      "documents": [
        {
          "file_name": "1、 商务视频彩铃一页纸长图介绍.png",
          "file_path": "D:\\GitHub_WorkSpace\\Test-System\\商务彩铃\\1、 商务视频彩铃一页纸长图介绍.png",
          "sha256": "文件hash",
          "status": "imported",
          "imported_at": "2026-05-08T00:00:00+08:00"
        }
      ]
    }
  ]
}
```

### 设计理由

- 每个知识库独立 `working_dir`，避免靠 `[数据库: xxx]` 前缀做伪隔离
- `/db/list` 直接读注册表
- `/search` 指定 database 时只查对应知识库
- 未指定 database 时按注册表遍历所有知识库，合并返回
- 删除或重建知识库时可以只删一个目录

---

## 3. 实施任务

### Task 1: 增加 RAG-Anything 依赖和启动检查

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\requirements.txt`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\start.py`

- [ ] **Step 1: 更新 requirements**

将 `requirements.txt` 改成：

```txt
fastapi>=0.104.0
uvicorn>=0.24.0
python-dotenv>=1.0.0
requests>=2.31.0
pydantic>=2.0.0
raganything
mineru[core]
```

如果执行时决定复用本地源码安装，则命令用：

```powershell
python -m pip install -e D:\GitHub_WorkSpace\RAG-Anything
python -m pip install -U "mineru[core]"
```

不建议在 `requirements.txt` 中写死 `D:\GitHub_WorkSpace\RAG-Anything`，避免换机器后路径失效；安装命令写入部署文档即可。

- [ ] **Step 2: 修改 start.py 依赖检查**

`start.py` 应检查：

```python
raganything_available = check_dependency("raganything", "raganything")
mineru_available = check_dependency("magic_pdf", "mineru[core]")
```

保留 FastAPI 和 uvicorn 检查。启动失败时提示：

```text
[WARN] raganything 未安装，请运行: python -m pip install -e D:\GitHub_WorkSpace\RAG-Anything
[WARN] MinerU 未安装，请运行: python -m pip install -U "mineru[core]"
```

- [ ] **Step 3: 验证依赖导入**

运行：

```powershell
python -c "from raganything import RAGAnything, RAGAnythingConfig; print('raganything ok')"
mineru --version
```

预期：

```text
raganything ok
mineru, version 3.x.x
```

---

### Task 2: 抽出数据库注册表

**Files:**
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\database_registry.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
- Test: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_database_registry.py`

- [ ] **Step 1: 创建测试**

创建 `tests/test_database_registry.py`：

```python
from pathlib import Path

from database_registry import DatabaseRegistry


def test_registry_starts_empty(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")

    assert registry.list_databases() == []


def test_register_database_and_document(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")

    registry.register_database("商务彩铃")
    registry.register_document(
        "商务彩铃",
        file_name="介绍.png",
        file_path="D:/data/介绍.png",
        sha256="abc123",
    )

    databases = registry.list_databases()
    assert len(databases) == 1
    assert databases[0]["id"] == "商务彩铃"
    assert databases[0]["engine"] == "raganything"
    assert databases[0]["documents"][0]["file_name"] == "介绍.png"


def test_register_database_deduplicates(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")

    registry.register_database("商务彩铃")
    registry.register_database("商务彩铃")

    assert len(registry.list_databases()) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python -m pytest tests\test_database_registry.py -v
```

预期：`ModuleNotFoundError: No module named 'database_registry'`

- [ ] **Step 3: 实现 registry**

创建 `database_registry.py`：

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DatabaseRegistry:
    def __init__(self, registry_file: str | Path):
        self.registry_file = Path(registry_file)
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.registry_file.exists():
            return {"databases": []}
        try:
            data = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"databases": []}
        if isinstance(data, list):
            return {
                "databases": [
                    {
                        "id": str(item),
                        "name": str(item),
                        "status": "active",
                        "engine": "raganything",
                        "documents": [],
                    }
                    for item in data
                ]
            }
        if not isinstance(data, dict):
            return {"databases": []}
        data.setdefault("databases", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.registry_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_databases(self) -> list[dict[str, Any]]:
        return self._load()["databases"]

    def get_database(self, database_id: str) -> dict[str, Any] | None:
        for database in self.list_databases():
            if database.get("id") == database_id:
                return database
        return None

    def register_database(self, database_id: str, name: str | None = None) -> dict[str, Any]:
        database_id = database_id.strip()
        if not database_id:
            raise ValueError("database_id must not be empty")

        data = self._load()
        for database in data["databases"]:
            if database.get("id") == database_id:
                return database

        now = datetime.now(timezone.utc).isoformat()
        database = {
            "id": database_id,
            "name": name or database_id,
            "status": "active",
            "engine": "raganything",
            "created_at": now,
            "updated_at": now,
            "documents": [],
        }
        data["databases"].append(database)
        self._save(data)
        return database

    def register_document(
        self,
        database_id: str,
        file_name: str,
        file_path: str,
        sha256: str,
    ) -> None:
        data = self._load()
        database = None
        for item in data["databases"]:
            if item.get("id") == database_id:
                database = item
                break
        if database is None:
            database = self.register_database(database_id)
            data = self._load()
            database = next(item for item in data["databases"] if item.get("id") == database_id)

        documents = database.setdefault("documents", [])
        documents[:] = [doc for doc in documents if doc.get("sha256") != sha256]
        documents.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "sha256": sha256,
                "status": "imported",
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        database["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(data)
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
python -m pytest tests\test_database_registry.py -v
```

预期：`3 passed`

---

### Task 3: 实现 RAGAnythingService 封装层

**Files:**
- Create: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\raganything_service.py`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\config.py`
- Test: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_raganything_service.py`

- [ ] **Step 1: 增加 config 配置**

在 `config.py` 增加：

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_ROOT = BASE_DIR / "storage"
RAGANYTHING_STORAGE_ROOT = STORAGE_ROOT / "raganything"
RAGANYTHING_OUTPUT_ROOT = BASE_DIR / "output"
DATABASE_REGISTRY_FILE = STORAGE_ROOT / "databases.json"

RAGANYTHING_SOURCE_DIR = os.getenv("RAGANYTHING_SOURCE_DIR", r"D:\GitHub_WorkSpace\RAG-Anything")
PARSER = os.getenv("PARSER", "mineru")
PARSE_METHOD = os.getenv("PARSE_METHOD", "auto")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")

CHUNK_SIZE = _safe_int(os.getenv("CHUNK_SIZE", "1200"), 1200)
CHUNK_OVERLAP_SIZE = _safe_int(os.getenv("CHUNK_OVERLAP_SIZE", "100"), 100)
EMBEDDING_MAX_TOKENS = _safe_int(os.getenv("EMBEDDING_MAX_TOKENS", "5000"), 5000)

ENABLE_IMAGE_PROCESSING = os.getenv("ENABLE_IMAGE_PROCESSING", "true").lower() == "true"
ENABLE_TABLE_PROCESSING = os.getenv("ENABLE_TABLE_PROCESSING", "true").lower() == "true"
ENABLE_EQUATION_PROCESSING = os.getenv("ENABLE_EQUATION_PROCESSING", "true").lower() == "true"
```

保留现有 MiniMax 和 SiliconFlow 配置，避免影响陪练系统。

- [ ] **Step 2: 创建 fake 测试**

创建 `tests/test_raganything_service.py`：

```python
from pathlib import Path

import pytest

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    def __init__(self):
        self.queries = []
        self.files = []

    async def _ensure_lightrag_initialized(self):
        return None

    async def aquery(self, question, mode="hybrid"):
        self.queries.append((question, mode))
        return "这是商务彩铃的资费回答"

    async def process_document_complete(self, file_path, output_dir, parse_method, display_stats, backend):
        self.files.append((file_path, output_dir, parse_method, backend))


@pytest.mark.asyncio
async def test_query_wraps_result(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db_id, _working_dir: FakeRAG(),
    )

    result = await service.query("商务彩铃", "资费是多少", mode="hybrid")

    assert result["database"] == "商务彩铃"
    assert result["results"][0]["metadata"]["source"] == "raganything"
    assert "资费回答" in result["results"][0]["text"]


@pytest.mark.asyncio
async def test_ingest_registers_document(tmp_path: Path):
    source_file = tmp_path / "介绍.txt"
    source_file.write_text("商务彩铃介绍", encoding="utf-8")
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db_id, _working_dir: FakeRAG(),
    )

    await service.ingest_file("商务彩铃", source_file)

    database = registry.get_database("商务彩铃")
    assert database is not None
    assert database["documents"][0]["file_name"] == "介绍.txt"
```

- [ ] **Step 3: 运行测试确认失败**

```powershell
python -m pytest tests\test_raganything_service.py -v
```

预期：`ModuleNotFoundError: No module named 'raganything_service'`

- [ ] **Step 4: 实现服务封装**

创建 `raganything_service.py`：

```python
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

import config
from database_registry import DatabaseRegistry


def _ensure_raganything_path() -> None:
    source_dir = Path(config.RAGANYTHING_SOURCE_DIR)
    if source_dir.exists() and str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RAGAnythingService:
    def __init__(
        self,
        storage_root: str | Path,
        output_root: str | Path,
        registry: DatabaseRegistry,
        rag_factory: Callable[[str, Path], Any] | None = None,
    ):
        self.storage_root = Path(storage_root)
        self.output_root = Path(output_root)
        self.registry = registry
        self.rag_factory = rag_factory or self._create_rag
        self._instances: dict[str, Any] = {}

    def _db_working_dir(self, database_id: str) -> Path:
        return self.storage_root / database_id / "rag_storage"

    def _db_output_dir(self, database_id: str) -> Path:
        return self.output_root / database_id

    def _create_rag(self, database_id: str, working_dir: Path):
        _ensure_raganything_path()
        from raganything import RAGAnything, RAGAnythingConfig
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        if config.HF_ENDPOINT:
            os.environ["HF_ENDPOINT"] = config.HF_ENDPOINT

        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            kwargs.pop("keyword_extraction", None)
            response = await openai_complete_if_cache(
                config.MINIMAX_MODEL_M27,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=config.MINIMAX_API_KEY,
                base_url=config.MINIMAX_BASE_URL,
                **kwargs,
            )
            if isinstance(response, str):
                response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            return response

        async def embedding_func_async(texts, **kwargs):
            return await openai_embed.func(
                texts=texts,
                model=config.SILICONFLOW_MODEL,
                base_url=config.SILICONFLOW_BASE_URL + "/v1"
                if not config.SILICONFLOW_BASE_URL.endswith("/v1")
                else config.SILICONFLOW_BASE_URL,
                api_key=config.SILICONFLOW_API_KEY,
                max_token_size=config.EMBEDDING_MAX_TOKENS,
            )

        embedding_func = EmbeddingFunc(
            embedding_dim=1024,
            max_token_size=config.EMBEDDING_MAX_TOKENS,
            func=embedding_func_async,
        )

        rag_config = RAGAnythingConfig(
            working_dir=str(working_dir),
            parser=config.PARSER,
            parse_method=config.PARSE_METHOD,
            enable_image_processing=config.ENABLE_IMAGE_PROCESSING,
            enable_table_processing=config.ENABLE_TABLE_PROCESSING,
            enable_equation_processing=config.ENABLE_EQUATION_PROCESSING,
        )

        return RAGAnything(
            config=rag_config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            lightrag_kwargs={
                "chunk_token_size": config.CHUNK_SIZE,
                "chunk_overlap_token_size": config.CHUNK_OVERLAP_SIZE,
            },
        )

    def get_rag(self, database_id: str):
        if database_id not in self._instances:
            working_dir = self._db_working_dir(database_id)
            working_dir.mkdir(parents=True, exist_ok=True)
            self._instances[database_id] = self.rag_factory(database_id, working_dir)
        return self._instances[database_id]

    async def query(self, database_id: str, query: str, mode: str = "hybrid", n_results: int = 10) -> dict[str, Any]:
        rag = self.get_rag(database_id)
        await rag._ensure_lightrag_initialized()
        answer = await rag.aquery(query, mode=mode)
        database = self.registry.get_database(database_id) or {}
        sources = [doc.get("file_name") for doc in database.get("documents", []) if doc.get("file_name")]
        return {
            "query": query,
            "database": database_id,
            "results": [
                {
                    "text": str(answer),
                    "metadata": {
                        "source": "raganything",
                        "database": database_id,
                        "mode": mode,
                        "sources": sources,
                    },
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }

    async def query_all(self, query: str, mode: str = "hybrid", n_results: int = 10) -> dict[str, Any]:
        merged = []
        for database in self.registry.list_databases():
            result = await self.query(database["id"], query, mode=mode, n_results=n_results)
            merged.extend(result["results"])
        return {"query": query, "results": merged[:n_results], "total_found": len(merged)}

    async def ingest_file(self, database_id: str, file_path: str | Path) -> dict[str, Any]:
        file_path = Path(file_path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(str(file_path))

        self.registry.register_database(database_id)
        rag = self.get_rag(database_id)
        output_dir = self._db_output_dir(database_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        await rag.process_document_complete(
            file_path=str(file_path),
            output_dir=str(output_dir),
            parse_method=config.PARSE_METHOD,
            display_stats=True,
            backend=config.MINERU_BACKEND,
        )
        self.registry.register_document(
            database_id,
            file_name=file_path.name,
            file_path=str(file_path),
            sha256=_sha256(file_path),
        )
        return {"status": "success", "database": database_id, "file": file_path.name}
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest tests\test_raganything_service.py -v
```

预期：`2 passed`

---

### Task 4: 保持 8003 HTTP API 合同，替换 app.py 内部引擎

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
- Test: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_api_contract.py`

- [ ] **Step 1: 写 API 合同测试**

创建 `tests/test_api_contract.py`：

```python
from fastapi.testclient import TestClient

import app


class FakeService:
    def list_databases(self):
        return [{"id": "商务彩铃", "name": "商务彩铃", "status": "active"}]

    async def query(self, database_id, query, mode="hybrid", n_results=10):
        return {
            "query": query,
            "database": database_id,
            "results": [
                {
                    "text": "商务彩铃资费为10元/月/线起",
                    "metadata": {"source": "raganything", "database": database_id, "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }

    async def query_all(self, query, mode="hybrid", n_results=10):
        return {
            "query": query,
            "results": [
                {
                    "text": "商务彩铃资费为10元/月/线起",
                    "metadata": {"source": "raganything", "database": "商务彩铃", "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }


def test_db_list_contract(monkeypatch):
    monkeypatch.setattr(app, "rag_service", FakeService())
    client = TestClient(app.app)

    response = client.get("/db/list")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert data["databases"][0]["id"] == "商务彩铃"


def test_ai_enhanced_search_contract(monkeypatch):
    monkeypatch.setattr(app, "rag_service", FakeService())
    client = TestClient(app.app)

    response = client.post(
        "/ai_enhanced_search",
        json={"query": "资费是多少", "n_results": 3, "database": "商务彩铃"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "资费是多少"
    assert data["results"][0]["metadata"]["source"] == "raganything"
    assert "10元" in data["results"][0]["text"]
```

- [ ] **Step 2: 运行测试确认当前失败**

```powershell
python -m pytest tests\test_api_contract.py -v
```

预期：当前 `app.py` 没有 `rag_service` 或行为不匹配，测试失败。

- [ ] **Step 3: 修改 app.py 初始化**

将全局变量从：

```python
rag_engine = None
```

改为：

```python
rag_service = None
```

启动时初始化：

```python
@app.on_event("startup")
async def startup_event():
    global rag_service
    try:
        from database_registry import DatabaseRegistry
        from raganything_service import RAGAnythingService

        registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
        rag_service = RAGAnythingService(
            storage_root=config.RAGANYTHING_STORAGE_ROOT,
            output_root=config.RAGANYTHING_OUTPUT_ROOT,
            registry=registry,
        )
        logger.info("RAG-Anything 官方引擎服务初始化完成")
    except Exception as e:
        logger.error(f"RAG-Anything 官方引擎初始化失败: {e}")
        rag_service = None
```

- [ ] **Step 4: 修改 `/db/list`**

```python
@app.get("/db/list")
async def list_databases():
    databases = rag_service.registry.list_databases() if rag_service else []
    return {
        "status": "success",
        "count": len(databases),
        "databases": [
            {
                "id": item["id"],
                "name": item.get("name", item["id"]),
                "status": item.get("status", "active"),
            }
            for item in databases
        ],
    }
```

- [ ] **Step 5: 修改 `/search`**

```python
@app.post("/search")
async def search(request: SearchRequest):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG-Anything 引擎未初始化")
    if request.database:
        return await rag_service.query(
            request.database,
            request.query,
            mode="hybrid",
            n_results=request.n_results,
        )
    return await rag_service.query_all(
        request.query,
        mode="hybrid",
        n_results=request.n_results,
    )
```

- [ ] **Step 6: 修改 `/ai_enhanced_search`**

```python
@app.post("/ai_enhanced_search")
async def ai_enhanced_search(request: SearchRequest):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG-Anything 引擎未初始化")
    if request.database:
        return await rag_service.query(
            request.database,
            request.query,
            mode="hybrid",
            n_results=request.n_results,
        )
    return await rag_service.query_all(
        request.query,
        mode="hybrid",
        n_results=request.n_results,
    )
```

- [ ] **Step 7: 修改 `/query` 和 `/db/search`**

`/query` 复用 `mode="hybrid"`，保持旧字段 `context`、`sources` 时可以从 `results[0]` 派生。

`/db/search` 如果 `merge_results=True`，调用 `query_all()`；否则仍返回统一 results。

- [ ] **Step 8: 运行 API 合同测试**

```powershell
python -m pytest tests\test_api_contract.py -v
```

预期：`2 passed`

---

### Task 5: 改造导入脚本为官方 RAG-Anything 流程

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\import_files.py`
- Optional Modify: `D:\GitHub_WorkSpace\Test-System\ingest_folder.py`
- Optional Modify: `D:\GitHub_WorkSpace\Test-System\direct_ingest.py`

- [ ] **Step 1: 保留 CLI 入参**

必须继续支持：

```powershell
python rag-anything-api\import_files.py "D:\GitHub_WorkSpace\Test-System\商务彩铃" --database "商务彩铃" --recursive
python rag-anything-api\import_files.py "D:\GitHub_WorkSpace\Test-System\商务彩铃\1、 商务视频彩铃一页纸长图介绍.png" --database "商务彩铃"
```

- [ ] **Step 2: 支持官方格式**

支持格式集合改为：

```python
SUPPORTED_FORMATS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff",
    ".tif", ".gif", ".webp",
}
```

- [ ] **Step 3: 调用 RAGAnythingService.ingest_file**

`import_files.py` 中不再读取文件文本、不再手动切块、不再 `rag.ainsert()`；改为：

```python
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService

registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
service = RAGAnythingService(
    storage_root=config.RAGANYTHING_STORAGE_ROOT,
    output_root=config.RAGANYTHING_OUTPUT_ROOT,
    registry=registry,
)
await service.ingest_file(database, file_path)
```

- [ ] **Step 4: 导入目录时逐文件处理**

每个文件失败只记录失败，不中断整个目录：

```python
for file_path in files:
    try:
        await service.ingest_file(database, file_path)
        success += 1
    except Exception as e:
        fail += 1
        logger.exception("导入失败: %s", file_path)
```

- [ ] **Step 5: 验证 PNG 不再需要 easyocr**

运行：

```powershell
cd D:\GitHub_WorkSpace\Test-System
python rag-anything-api\import_files.py "D:\GitHub_WorkSpace\Test-System\商务彩铃" --database "商务彩铃" --recursive
```

预期：

```text
处理文件: 1、 商务视频彩铃一页纸长图介绍.png
RAGAnything 初始化成功
文件处理完成
导入完成：成功 1，失败 0
```

---

### Task 6: 增加可选 HTTP 导入接口

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\app.py`
- Test: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\tests\test_api_contract.py`

- [ ] **Step 1: 增加请求模型**

```python
class FileIngestRequest(BaseModel):
    path: str
    database: str
    recursive: bool = False
```

- [ ] **Step 2: 增加 `/ingest/path`**

```python
@app.post("/ingest/path")
async def ingest_path(request: FileIngestRequest):
    if not rag_service:
        raise HTTPException(status_code=503, detail="RAG-Anything 引擎未初始化")
    path = Path(request.path)
    if path.is_file():
        return await rag_service.ingest_file(request.database, path)
    if path.is_dir():
        # 遍历支持格式并导入
        ...
    raise HTTPException(status_code=404, detail=f"路径不存在: {request.path}")
```

该接口不是陪练/方案/出题必须依赖，但方便后续在浏览器或脚本里新建知识库。

---

### Task 7: 迁移当前“商务彩铃”知识库到官方 RAG-Anything

**Files/Data:**
- Source: `D:\GitHub_WorkSpace\Test-System\商务彩铃`
- Backup: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\lightrag_backup_YYYYMMDD_HHMMSS`
- New Storage: `D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\raganything\商务彩铃`

- [ ] **Step 1: 停止 8003**

```powershell
$conn = Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force }
```

- [ ] **Step 2: 备份旧 LightRAG 存储**

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Move-Item `
  -LiteralPath "D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\lightrag" `
  -Destination "D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\lightrag_backup_$stamp"
```

- [ ] **Step 3: 清空新存储中的同名库**

只删除：

```text
D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\raganything\商务彩铃
```

删除前必须用 `Resolve-Path` 确认最终路径在 `D:\GitHub_WorkSpace\Test-System\rag-anything-api\storage\raganything` 下。

- [ ] **Step 4: 使用官方 RAG-Anything 导入**

```powershell
python rag-anything-api\import_files.py "D:\GitHub_WorkSpace\Test-System\商务彩铃" --database "商务彩铃" --recursive
```

- [ ] **Step 5: 启动 8003**

```powershell
cd D:\GitHub_WorkSpace\Test-System\rag-anything-api
python start.py
```

- [ ] **Step 6: 验证知识库列表**

```powershell
Invoke-RestMethod http://localhost:8003/db/list | ConvertTo-Json -Depth 5
```

预期：

```json
{
  "status": "success",
  "count": 1,
  "databases": [
    {
      "id": "商务彩铃",
      "name": "商务彩铃",
      "status": "active"
    }
  ]
}
```

---

### Task 8: 端到端业务验证

**Files:**
- Existing: `D:\GitHub_WorkSpace\Test-System\test_service.py`
- Existing: `D:\GitHub_WorkSpace\Test-System\test_database_chinese.py`
- Existing: `D:\GitHub_WorkSpace\Test-System\ai-tutor-system\tutor_backend.py`
- Existing Skills: `solution-generator-skill/SKILL.md`, `peixun-skill/SKILL.md`

- [ ] **Step 1: RAG 服务健康检查**

```powershell
Invoke-RestMethod http://localhost:8003/health | ConvertTo-Json
Invoke-RestMethod http://localhost:8003/status | ConvertTo-Json -Depth 5
```

预期：

```json
{
  "status": "healthy",
  "engine": "ready"
}
```

`/status` 的 engine 字段应能看出使用 `RAGAnything + LightRAG`。

- [ ] **Step 2: 检索验证**

```powershell
$body = @{
  query = "商务视频彩铃产品资费是多少"
  n_results = 3
  database = "商务彩铃"
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8003/ai_enhanced_search -Method Post -Body $body -ContentType "application/json; charset=utf-8" | ConvertTo-Json -Depth 8
```

预期：

- 返回 HTTP 200
- `results[0].metadata.source = "raganything"`
- 回答中包含 `10元/月/线`、`25元/月/线`、`50元/月/线` 中至少一个
- metadata 中包含来源文件名

- [ ] **Step 3: 陪练系统验证**

```powershell
Invoke-RestMethod http://localhost:8002/api/status | ConvertTo-Json -Depth 5
```

预期：

```json
{
  "status": "running",
  "rag_service": "http://localhost:8003"
}
```

然后在前端完成一次“商务彩铃”相关陪练，确认结束报告不再提示 RAG 服务未启动。

- [ ] **Step 4: 方案生成 skill 验证**

使用 `solution-generator-skill` 中现有命令：

```powershell
$body = @{
  query = "商务视频彩铃 产品介绍 功能 优势"
  n_results = 5
  database = "商务彩铃"
} | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:8003/ai_enhanced_search" -Method POST -Body $body -ContentType "application/json" | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

预期：返回仍是原来的 `results` 数组格式，方案 skill 无需改 Python 调用。

- [ ] **Step 5: 培训/考试出题 skill 验证**

使用 `peixun-skill` 中现有命令：

```powershell
curl -s -X POST http://localhost:8003/search `
  -H "Content-Type: application/json" `
  -d '{"query": "商务视频彩铃资费和卖点", "n_results": 5, "database": "商务彩铃"}'
```

预期：返回 JSON 中仍有 `results`。

---

### Task 9: 文档更新

**Files:**
- Modify: `D:\GitHub_WorkSpace\Test-System\部署说明.md`
- Modify: `D:\GitHub_WorkSpace\Test-System\rag_database_guide.md`
- Modify: `D:\GitHub_WorkSpace\Test-System\使用说明.md`
- Modify: `D:\GitHub_WorkSpace\Test-System\未来优化方向.md`

- [ ] **Step 1: 部署说明写清依赖**

必须包含：

```powershell
python -m pip install -e D:\GitHub_WorkSpace\RAG-Anything
python -m pip install -U "mineru[core]"
python -c "from raganything import RAGAnything; print('OK')"
mineru --version
```

- [ ] **Step 2: 写清可选外部依赖**

Office 文档需要 LibreOffice：

```text
doc/docx/ppt/pptx/xls/xlsx 解析依赖 LibreOffice。
图片/PDF 使用 MinerU pipeline 后端。
```

- [ ] **Step 3: 写清新建知识库命令**

```powershell
python rag-anything-api\import_files.py "资料文件夹或文件路径" --database "知识库名称" --recursive
```

- [ ] **Step 4: 写清技术事实**

文档中统一表述：

```text
知识库技术栈：HKUDS/RAG-Anything + MinerU + LightRAG。
8003 是 Test-System 的兼容 REST API 层，业务系统不直接调用 RAG-Anything Python API。
```

---

## 4. 回滚方案

### 可回滚范围

本计划不恢复旧 `rag-core`，只回滚 8003 内部实现到当前手写 LightRAG 兼容层。

### 回滚步骤

1. 停止 8003。
2. 恢复修改前的 `rag-anything-api/app.py`、`config.py`、`import_files.py`、`start.py`。
3. 将 `storage/lightrag_backup_YYYYMMDD_HHMMSS` 改回 `storage/lightrag`。
4. 启动 8003。
5. 验证 `/db/list`、`/search`、`/ai_enhanced_search`。

---

## 5. 风险和处理

### 风险 1: MinerU 首次处理慢

原因：首次下载模型、CPU 跑 pipeline 慢。

处理：
- 首次导入单独跑，不影响 8002 陪练。
- 导入期间停止 8003，导入完成后再启服务。
- 后续可做后台任务队列，但本次先保证链路打通。

### 风险 2: 图片解析结果不如手工 OCR 稳定

处理：
- 优先使用官方 MinerU pipeline。
- 如果某张图解析失败，保留人工 OCR 文本作为补充文档导入，但 metadata 标明来源。

### 风险 3: RAG-Anything 返回的是生成答案，不是传统 top-k chunk

处理：
- 业务 API 继续用 `results` 包一层。
- `results[0].text` 放 RAG-Anything 答案。
- `metadata.sources` 放注册表里相关资料文件名。
- 后续如需要更细来源，再研究 RAG-Anything/Lightrag context 返回结构。

### 风险 4: 多知识库隔离

处理：
- 每个 database 使用独立 `working_dir`。
- 禁止多个库共用一个 LightRAG 存储再靠文本前缀过滤。

---

## 6. 验收标准

全部满足才算完成：

- `python -c "from raganything import RAGAnything; print('OK')"` 成功
- `mineru --version` 成功
- `http://localhost:8003/status` 显示官方 RAG-Anything 引擎 ready
- `http://localhost:8003/db/list` 显示新建知识库
- `POST /ai_enhanced_search` 兼容原返回结构
- 陪练系统 `http://localhost:8002/api/status` 仍指向 `http://localhost:8003`
- 方案生成 skill 的 `Invoke-WebRequest` 命令不需要改 URL
- 培训/考试出题 skill 的 `curl` 命令不需要改 URL
- 图片长图可以不经过 easyocr，直接由 RAG-Anything/MinerU 流程导入
- 查询“商务视频彩铃产品资费是多少”能返回资费信息

---

## 7. 建议执行顺序

1. 先执行 Task 1-4，只替换服务内部引擎，不导入正式资料。
2. 再执行 Task 5，用一张 PNG 测试官方导入链路。
3. 再执行 Task 7，重建“商务彩铃”知识库。
4. 最后执行 Task 8-9，做业务链路验证和文档更新。

这样每一步都有可回退点，不会一次性把陪练、方案、出题链路全部打断。
