"""
RAG-Anything REST API 服务
保留既有接口合同，内部引擎使用 HKUDS/RAG-Anything
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# 设置编码。不要 detach 标准流，uvicorn/logging 可能已经持有这些 stream。
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
import config
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content):
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="RAG-Anything 智能检索系统",
    description="基于 HKUDS/RAG-Anything 的增强检索服务",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


rag_service: Optional[RAGAnythingService] = None
registry: Optional[DatabaseRegistry] = None
startup_error: Optional[str] = None


def _normalize_database_id(text: Optional[str]) -> str:
    return str(text or "").strip()


def _query_mode() -> str:
    mode = str(getattr(config, "DEFAULT_QUERY_MODE", "naive")).strip().lower()
    return mode or "naive"


def _ensure_registry_seeded() -> None:
    """首次运行时迁移旧列表，并在缺失时写入默认项。"""
    assert registry is not None

    if config.DATABASE_REGISTRY_FILE.exists():
        return

    legacy_file = config.LEGACY_LIGHTRAG_DIR / "databases.json"
    if legacy_file.exists():
        try:
            legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
            if isinstance(legacy, list):
                for db_id in legacy:
                    db_id = _normalize_database_id(db_id)
                    if db_id:
                        registry.register_database(
                            db_id,
                            working_dir=str(config.RAGANYTHING_STORAGE_ROOT / db_id / "rag_storage"),
                            output_dir=str(config.RAGANYTHING_OUTPUT_ROOT / db_id),
                        )
                return
        except (json.JSONDecodeError, OSError):
            pass

    for db_id in config.DEFAULT_DATABASE_IDS:
        registry.register_database(
            db_id,
            working_dir=str(config.RAGANYTHING_STORAGE_ROOT / db_id / "rag_storage"),
            output_dir=str(config.RAGANYTHING_OUTPUT_ROOT / db_id),
        )


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


class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 10
    database: Optional[str] = None


class MultiSearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5
    merge_results: Optional[bool] = False


class DocumentIngestRequest(BaseModel):
    text: str
    database: Optional[str] = "default"
    source: Optional[str] = "manual"


class FileIngestRequest(BaseModel):
    path: str
    database: str
    recursive: bool = False


def _require_service() -> RAGAnythingService:
    if not rag_service:
        detail = "RAG-Anything 引擎未初始化"
        if startup_error:
            detail = f"{detail}: {startup_error}"
        raise HTTPException(status_code=503, detail=detail)
    return rag_service


def _to_legacy_query_response(result: dict, include_context: bool = False) -> dict:
    payload = {
        "query": result.get("query", ""),
        "results": result.get("results", []),
        "total_found": result.get("total_found", 0),
    }
    if "database" in result:
        payload["database"] = result.get("database")
        payload["enhanced_queries"] = [payload["query"]]
    if include_context:
        first = (result.get("results") or [{}])[0]
        payload["context"] = first.get("text", "")
        payload["sources"] = [
            {
                "source": first.get("metadata", {}).get("source", "raganything"),
                "database": first.get("metadata", {}).get("database", "all"),
            }
        ] if first else []
    return payload


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "RAG-Anything 智能检索系统正在运行",
        "version": "3.0.0",
        "engine": "RAGAnything + MinerU + LightRAG",
        "llm": f"MiniMax ({config.MINIMAX_MODEL_M27} → {config.MINIMAX_MODEL_M25})",
        "embedding": f"硅基流动 {config.SILICONFLOW_MODEL}",
        "endpoints": {
            "docs": "/docs",
            "search": "/search",
            "ai_enhanced_search": "/ai_enhanced_search",
            "query": "/query",
            "db_list": "/db/list",
            "db_stats": "/db/stats",
            "ingest_path": "/ingest/path",
        },
    }


@app.post("/search")
async def search(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        if db_id:
            result = await service.query(db_id, request.query, mode=_query_mode(), n_results=request.n_results or 10)
        else:
            result = await service.query_all(request.query, mode=_query_mode(), n_results=request.n_results or 10)
        return _to_legacy_query_response(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai_enhanced_search")
async def ai_enhanced_search(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        if db_id:
            result = await service.query(db_id, request.query, mode=_query_mode(), n_results=request.n_results or 10)
        else:
            result = await service.query_all(request.query, mode=_query_mode(), n_results=request.n_results or 10)
        return _to_legacy_query_response(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error(f"AI增强搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def query(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        if db_id:
            result = await service.query(db_id, request.query, mode=_query_mode(), n_results=request.n_results or 10)
        else:
            result = await service.query_all(request.query, mode=_query_mode(), n_results=request.n_results or 10)
        return _to_legacy_query_response(result, include_context=True)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error(f"RAG查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def status():
    return {
        "status": "running",
        "engine": "ready" if rag_service else "not_initialized",
        "message": "RAG-Anything 智能检索系统",
        "engine_stack": "RAGAnything + MinerU + LightRAG",
        "llm": {
            "primary": config.MINIMAX_MODEL_M27,
            "fallback": config.MINIMAX_MODEL_M25,
            "timeout_m27": config.LLM_TIMEOUT_M27,
            "timeout_m25": config.LLM_TIMEOUT_M25,
        },
        "embedding": {
            "provider": "硅基流动",
            "model": config.SILICONFLOW_MODEL,
            "max_tokens": config.EMBEDDING_MAX_TOKENS,
        },
        "storage": {
            "registry": str(config.DATABASE_REGISTRY_FILE),
            "root": str(config.RAGANYTHING_STORAGE_ROOT),
        },
        "startup_error": startup_error,
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "engine": "ready" if rag_service else "not_initialized"}


@app.get("/db/list")
async def list_databases():
    service = _require_service()
    data = service.registry.list_databases()
    databases = [
        {
            "id": item.get("id"),
            "name": item.get("name", item.get("id")),
            "status": item.get("status", "active"),
        }
        for item in data
        if item.get("id")
    ]
    return {"status": "success", "count": len(databases), "databases": databases}


@app.get("/db/stats")
async def get_all_database_stats():
    service = _require_service()
    stats = {}
    for item in service.registry.list_databases():
        db_id = item.get("id")
        if not db_id:
            continue
        stats[db_id] = {
            "name": item.get("name", db_id),
            "status": item.get("status", "active"),
            "engine": item.get("engine", "raganything"),
            "documents": len(item.get("documents", [])),
            "working_dir": item.get("working_dir", ""),
            "output_dir": item.get("output_dir", ""),
            "updated_at": item.get("updated_at"),
        }
    return {"status": "success", "databases": stats}


@app.get("/db/stats/{db_id}")
@app.get("/db/{db_id}/stats")
async def get_database_stats(db_id: str):
    service = _require_service()
    item = service.registry.get_database(db_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    return {
        "status": "success",
        "database": {
            "id": item.get("id"),
            "name": item.get("name", item.get("id")),
            "status": item.get("status", "active"),
            "engine": item.get("engine", "raganything"),
            "documents": len(item.get("documents", [])),
            "working_dir": item.get("working_dir", ""),
            "output_dir": item.get("output_dir", ""),
            "updated_at": item.get("updated_at"),
        },
    }


@app.post("/db/search")
async def multi_database_search(request: MultiSearchRequest):
    service = _require_service()
    try:
        result = await service.query_all(
            request.query,
            mode=_query_mode(),
            n_results=request.top_k or 5,
        )
        payload = _to_legacy_query_response(result)
        payload["merged"] = request.merge_results
        return payload
    except Exception as e:
        logger.error(f"多数据库搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/text")
async def ingest_text(request: DocumentIngestRequest):
    service = _require_service()
    database = _normalize_database_id(request.database) or "default"

    try:
        result = await service.ingest_text(database, request.text, source=request.source or "manual")
        return {
            "status": result.get("status", "success"),
            "database": database,
            "source": request.source,
            "message": "文本已导入知识库",
        }
    except Exception as e:
        logger.error(f"文本导入失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/path")
async def ingest_path(request: FileIngestRequest):
    service = _require_service()
    db_id = _normalize_database_id(request.database)
    if not db_id:
        raise HTTPException(status_code=400, detail="database 不能为空")

    path = Path(request.path)
    if path.is_file():
        try:
            return await service.ingest_file(db_id, path)
        except Exception as e:
            logger.error(f"文件导入失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if path.is_dir():
        from import_files import SUPPORTED_FORMATS

        files = []
        if request.recursive:
            for root, _, names in os.walk(path):
                for name in names:
                    if Path(name).suffix.lower() in SUPPORTED_FORMATS:
                        files.append(Path(root) / name)
        else:
            for child in path.iterdir():
                if child.is_file() and child.suffix.lower() in SUPPORTED_FORMATS:
                    files.append(child)

        total = len(files)
        success = 0
        failures = []
        for file_path in files:
            try:
                await service.ingest_file(db_id, file_path)
                success += 1
            except Exception as e:
                failures.append({"file": str(file_path), "error": str(e)})

        return {
            "status": "success" if not failures else "partial_success",
            "database": db_id,
            "total_files": total,
            "success_files": success,
            "failed_files": len(failures),
            "failures": failures[:20],
        }

    raise HTTPException(status_code=404, detail=f"路径不存在: {request.path}")


def check_port_available(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except socket.error:
            return False


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  RAG-Anything 智能检索系统")
    print("=" * 60)
    print()
    print(f"  Engine: RAGAnything + MinerU + LightRAG")
    print(f"  LLM: {config.MINIMAX_MODEL_M27} → {config.MINIMAX_MODEL_M25}")
    print(f"  Embedding: 硅基流动 {config.SILICONFLOW_MODEL}")
    print(f"  Registry: {config.DATABASE_REGISTRY_FILE}")
    print()

    if not check_port_available(config.RAG_SERVICE_PORT):
        print(f"[ERROR] 端口 {config.RAG_SERVICE_PORT} 已被占用！")
        sys.exit(1)

    print(f"  API地址: http://{config.RAG_SERVICE_HOST}:{config.RAG_SERVICE_PORT}")
    print(f"  API文档: http://{config.RAG_SERVICE_HOST}:{config.RAG_SERVICE_PORT}/docs")
    print()

    uvicorn.run(
        app,
        host=config.RAG_SERVICE_HOST,
        port=config.RAG_SERVICE_PORT,
        log_level="info",
    )
