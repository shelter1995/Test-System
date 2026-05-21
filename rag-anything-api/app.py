"""
RAG-Anything REST API 服务
保留既有接口合同，内部引擎使用 HKUDS/RAG-Anything
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# 设置编码。不要 detach 标准流，uvicorn/logging 可能已经持有这些 stream。
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
import config
from database_registry import DatabaseRegistry
from progress import progress_tracker
from rag_engines.factory import create_traditional_engine, database_engine_name
from raganything_service import RAGAnythingService
from kb_answer import build_context_fallback_answer, build_kb_answer_prompt, extract_source_summaries
from model_settings import ModelSettingsStore
from rag_engines.traditional.model_clients import ModelEndpoint, OpenAICompatibleClient

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


rag_service: Optional[RAGAnythingService] = None
traditional_service = None
registry: Optional[DatabaseRegistry] = None
startup_error: Optional[str] = None


async def initialize_service() -> None:
    global rag_service, traditional_service, registry, startup_error
    try:
        registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
        _ensure_registry_seeded()
        rag_service = RAGAnythingService(
            storage_root=config.RAGANYTHING_STORAGE_ROOT,
            output_root=config.RAGANYTHING_OUTPUT_ROOT,
            registry=registry,
        )
        _recover_interrupted_processing_documents(rag_service)
        traditional_service = create_traditional_engine()
        startup_error = None
        logger.info("RAG-Anything 服务初始化完成")
    except Exception as e:
        rag_service = None
        traditional_service = None
        startup_error = str(e)
        logger.error(f"RAG-Anything 服务初始化失败: {e}")


@asynccontextmanager
async def lifespan(app_: FastAPI):
    await initialize_service()
    yield


app = FastAPI(
    title="RAG-Anything 智能检索系统",
    description="基于 HKUDS/RAG-Anything 的增强检索服务",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings_store = ModelSettingsStore(
    config.STORAGE_ROOT / "model_settings.json",
    config.STORAGE_ROOT / "model_settings.local.json",
)


def _normalize_database_id(text: Optional[str]) -> str:
    return str(text or "").strip()


def _normalize_engine_name(text: Optional[str]) -> str | None:
    engine = str(text or "").strip().lower()
    if not engine:
        return None
    if engine not in {"traditional", "raganything"}:
        raise HTTPException(status_code=400, detail=f"不支持的 RAG 引擎: {engine}")
    return engine


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _query_mode() -> str:
    mode = str(getattr(config, "DEFAULT_QUERY_MODE", "naive")).strip().lower()
    return mode or "naive"


def _ensure_registry_seeded() -> None:
    """Seed registry and recover databases that already exist on disk."""
    assert registry is not None

    def register_raganything_database(db_id: str) -> None:
        kwargs = {
            "working_dir": str(config.RAGANYTHING_STORAGE_ROOT / db_id / "rag_storage"),
            "output_dir": str(config.RAGANYTHING_OUTPUT_ROOT / db_id),
        }
        try:
            item = registry.register_database(db_id, engine="raganything", **kwargs)
        except TypeError:
            item = registry.register_database(db_id, **kwargs)
            if isinstance(item, dict):
                item["engine"] = "raganything"

    should_discover_existing_dirs = not config.DATABASE_REGISTRY_FILE.exists()
    if should_discover_existing_dirs:
        legacy_file = config.LEGACY_LIGHTRAG_DIR / "databases.json"
        if legacy_file.exists():
            try:
                legacy = json.loads(legacy_file.read_text(encoding="utf-8"))
                if isinstance(legacy, list):
                    for db_id in legacy:
                        db_id = _normalize_database_id(db_id)
                        if db_id:
                            register_raganything_database(db_id)
            except (json.JSONDecodeError, OSError):
                pass

        for db_id in config.DEFAULT_DATABASE_IDS:
            register_raganything_database(db_id)

        discovered = set()
        for root in (config.RAGANYTHING_STORAGE_ROOT, config.RAGANYTHING_OUTPUT_ROOT):
            if not root.exists():
                continue
            for path in root.iterdir():
                if not path.is_dir() or path.name == "files":
                    continue
                db_id = _normalize_database_id(path.name)
                if db_id:
                    discovered.add(db_id)

        for db_id in sorted(discovered):
            register_raganything_database(db_id)


class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 10
    database: Optional[str] = None
    enable_rerank: Optional[bool] = None
    vlm_enhanced: Optional[bool] = None  # 默认自动（有 VLM 就用），可显式关闭


class MultiSearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5
    merge_results: Optional[bool] = False


class KBChatRequest(BaseModel):
    query: str
    database: str
    n_results: Optional[int] = 5
    history: Optional[List[dict]] = None


class DocumentIngestRequest(BaseModel):
    text: str
    database: Optional[str] = "default"
    source: Optional[str] = "manual"


class FileIngestRequest(BaseModel):
    path: str
    database: str
    recursive: bool = False


class DatabaseRegisterRequest(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = ""
    engine: Optional[str] = None


class DatabaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    engine: Optional[str] = None


class RetryDocumentRequest(BaseModel):
    strategy: str = "markdown_segments"
    max_chars: int = 12000


def _database_payload(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description", ""),
        "status": item.get("status"),
        "engine": item.get("engine"),
        "documents": item.get("documents", []),
        "working_dir": item.get("working_dir", ""),
        "output_dir": item.get("output_dir", ""),
        "updated_at": item.get("updated_at"),
    }


def _require_service() -> RAGAnythingService:
    if not rag_service:
        detail = "RAG-Anything 引擎未初始化"
        if startup_error:
            detail = f"{detail}: {startup_error}"
        raise HTTPException(status_code=503, detail=detail)
    return rag_service


def _engine_for_database(db_id: str):
    service = _require_service()
    item = service.registry.get_database(db_id)
    engine = database_engine_name(item)
    if engine == "traditional":
        if traditional_service is None:
            raise HTTPException(status_code=503, detail="传统 RAG 引擎未初始化")
        return traditional_service
    return service


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


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def _trim_snippet(text: str, max_chars: int = 220) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."


def _is_success_ingest_status(status: str) -> bool:
    return str(status or "").strip() in {"success", "已导入"}


def _record_traditional_ingest_result(
    service: Any,
    db_id: str,
    file_path: Path,
    result: dict[str, Any],
    *,
    existing_sha256: str | None = None,
    source_name: str | None = None,
) -> None:
    sha256 = str(existing_sha256 or result.get("document_sha256") or _sha256(file_path))
    status = str(result.get("status") or "").strip()
    is_success = _is_success_ingest_status(status)
    registry_status = "已导入" if is_success else "error"
    error = "" if is_success else str(result.get("error") or result.get("message") or "传统 RAG 导入失败")
    engine = str(result.get("engine") or "traditional")
    chunk_count = int(result.get("chunk_count") or 0)
    embedding_model = str(result.get("embedding_model") or "")
    rerank_model = str(result.get("rerank_model") or "")

    if existing_sha256:
        service.registry.update_document_status(db_id, sha256, status=registry_status, error=error)
        update_index = getattr(service.registry, "update_document_index_metadata", None)
        if callable(update_index):
            update_index(
                db_id,
                sha256,
                engine=engine,
                index_status="indexed" if is_success else "error",
                chunk_count=chunk_count,
                embedding_model=embedding_model,
                rerank_model=rerank_model,
            )
        return

    service.registry.register_document(
        db_id,
        file_name=source_name or file_path.name,
        stored_file_name=file_path.name,
        file_path=str(file_path),
        sha256=sha256,
        source=source_name or file_path.name,
        status=registry_status,
        error=error,
        engine=engine,
        chunk_count=chunk_count,
        embedding_model=embedding_model,
        rerank_model=rerank_model,
    )


def _is_indexed_traditional_document(doc: dict[str, Any]) -> bool:
    return (
        str(doc.get("engine") or "").strip().lower() == "traditional"
        and str(doc.get("index_status") or "").strip().lower() == "indexed"
        and int(doc.get("chunk_count") or 0) > 0
    )


def _finalize_indexed_traditional_document(service: Any, db_id: str, sha256: str) -> None:
    service.registry.update_document_status(db_id, sha256, status="已导入", error="")
    service.registry.update_document_progress(db_id, sha256, stage="done")


async def _resolve_kb_chat_context(request: KBChatRequest) -> dict[str, Any]:
    db_id = _normalize_database_id(request.database)
    if not db_id:
        raise HTTPException(status_code=400, detail="database 不能为空")

    query_text = str(request.query or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="query 不能为空")

    engine = _engine_for_database(db_id)
    retrieve_contexts = getattr(engine, "retrieve_contexts", None)
    if callable(retrieve_contexts):
        try:
            contexts = await retrieve_contexts(
                db_id,
                request.query,
                history=request.history or [],
            )
        except TypeError:
            contexts = await retrieve_contexts(db_id, request.query)
        if isinstance(contexts, dict):
            context_result = contexts
        else:
            context_list = contexts if isinstance(contexts, list) else []
            context_result = {
                "query": request.query,
                "database": db_id,
                "contexts": context_list,
                "total_found": len(context_list),
                "fallback": None,
            }
    else:
        context_result = await engine.query_context(
            db_id,
            request.query,
            mode=config.CONTEXT_QUERY_MODE,
            max_chars=config.CONTEXT_MAX_CHARS,
        )

    contexts = context_result.get("contexts") or []
    return {
        "db_id": db_id,
        "context_result": context_result,
        "contexts": contexts,
        "sources": extract_source_summaries(contexts),
    }


async def _generate_kb_answer_stream(service: Any, prompt: str):
    stream_answer = getattr(service, "generate_answer_stream", None)
    if callable(stream_answer):
        async for token in _without_think_tokens(stream_answer(prompt)):
            if token:
                yield token
        return

    answer = str(await service.generate_answer(prompt) or "").strip()
    if answer:
        yield answer


async def _without_think_tokens(tokens):
    buffer = ""
    in_think = False
    start_tag = "<think>"
    end_tag = "</think>"
    keep_tail = max(len(start_tag), len(end_tag)) - 1

    async for token in tokens:
        buffer += str(token or "")
        while buffer:
            lower = buffer.lower()
            if in_think:
                end_index = lower.find(end_tag)
                if end_index == -1:
                    break
                buffer = buffer[end_index + len(end_tag):]
                in_think = False
                continue

            start_index = lower.find(start_tag)
            if start_index != -1:
                visible = buffer[:start_index]
                if visible:
                    yield visible
                buffer = buffer[start_index + len(start_tag):]
                in_think = True
                continue

            if len(buffer) <= keep_tail:
                break
            visible = buffer[:-keep_tail]
            buffer = buffer[-keep_tail:]
            if visible:
                yield visible

    if buffer and not in_think:
        yield buffer


@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "RAG-Anything 智能检索系统正在运行",
        "version": "3.1.0",
        "engine": "RAGAnything + MinerU + LightRAG",
        "llm": f"MiniMax ({config.MINIMAX_MODEL_M27} → {config.MINIMAX_MODEL_M25})",
        "embedding": f"硅基流动 {config.SILICONFLOW_MODEL}",
        "query": {
            "default_mode": config.DEFAULT_QUERY_MODE,
            "vlm": "enabled" if config.ENABLE_VLM and config.VLM_API_KEY else "disabled",
            "rerank": "enabled" if config.ENABLE_RERANK and config.RERANK_API_KEY else "disabled",
        },
        "endpoints": {
            "docs": "/docs",
            "search": "/search",
            "ai_enhanced_search": "/ai_enhanced_search",
            "query": "/query",
            "kb_chat": "/kb/chat",
            "db_list": "/db/list",
            "db_stats": "/db/stats",
            "ingest_path": "/ingest/path",
            "ingest_upload": "/ingest/upload",
        },
    }


def _build_query_kwargs(request: SearchRequest) -> dict:
    """从请求体提取查询参数。"""
    kwargs = {"mode": _query_mode(), "n_results": request.n_results or 10}
    if request.enable_rerank is not None:
        kwargs["enable_rerank"] = request.enable_rerank
    if request.vlm_enhanced is not None:
        kwargs["vlm_enhanced"] = request.vlm_enhanced
    return kwargs


@app.post("/search")
async def search(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        kwargs = _build_query_kwargs(request)
        if db_id:
            engine = _engine_for_database(db_id)
            result = await engine.query(db_id, request.query, **kwargs)
        else:
            result = await service.query_all(request.query, **kwargs)
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
        kwargs = _build_query_kwargs(request)
        if db_id:
            engine = _engine_for_database(db_id)
            result = await engine.query(db_id, request.query, **kwargs)
        else:
            result = await service.query_all(request.query, **kwargs)
        return _to_legacy_query_response(result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error(f"AI增强搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/context")
async def context(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        if not db_id:
            raise HTTPException(status_code=400, detail="database 不能为空")
        engine = _engine_for_database(db_id)
        result = await engine.query_context(
            db_id,
            request.query,
            mode=config.CONTEXT_QUERY_MODE,
            max_chars=config.CONTEXT_MAX_CHARS,
        )
        result.setdefault("fallback", "")
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上下文检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query")
async def query(request: SearchRequest):
    service = _require_service()
    try:
        db_id = _normalize_database_id(request.database)
        kwargs = _build_query_kwargs(request)
        if db_id:
            engine = _engine_for_database(db_id)
            result = await engine.query(db_id, request.query, **kwargs)
        else:
            result = await service.query_all(request.query, **kwargs)
        return _to_legacy_query_response(result, include_context=True)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error(f"RAG查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/kb/chat")
async def kb_chat(request: KBChatRequest):
    service = _require_service()
    try:
        prepared = await _resolve_kb_chat_context(request)
        db_id = prepared["db_id"]
        context_result = prepared["context_result"]
        contexts = prepared["contexts"]
        sources = prepared["sources"]
        answer_fallback = context_result.get("fallback")
        if contexts:
            prompt = build_kb_answer_prompt(request.query, contexts, request.history or [])
            try:
                answer = str(await service.generate_answer(prompt) or "").strip()
            except Exception as exc:
                logger.warning("知识库答案生成失败，改用上下文摘要兜底: %s", exc)
                answer = build_context_fallback_answer(request.query, contexts)
                answer_fallback = "answer_generation_failed"
        else:
            answer = "当前知识库未找到相关资料。"
            answer_fallback = answer_fallback or "no_result"

        answer = answer or "当前知识库未找到相关资料。"

        return {
            "query": request.query,
            "database": db_id,
            "answer": answer,
            "sources": sources,
            "total_sources": len(sources),
            "fallback": answer_fallback,
            "sources_fallback": context_result.get("fallback"),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"知识库问答失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/kb/chat/stream")
async def kb_chat_stream(request: KBChatRequest):
    service = _require_service()
    db_id = _normalize_database_id(request.database)
    if not db_id:
        raise HTTPException(status_code=400, detail="database 不能为空")
    if not str(request.query or "").strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    async def event_stream():
        answer = ""
        context_result: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        answer_fallback = None
        try:
            yield _sse_event("status", {"stage": "retrieving", "message": "正在检索知识库..."})
            prepared = await _resolve_kb_chat_context(request)
            context_result = prepared["context_result"]
            contexts = prepared["contexts"]
            sources = prepared["sources"]
            answer_fallback = context_result.get("fallback")
            yield _sse_event(
                "sources",
                {
                    "sources": sources,
                    "total_sources": len(sources),
                    "fallback": answer_fallback,
                    "sources_fallback": context_result.get("fallback"),
                },
            )

            if contexts:
                prompt = build_kb_answer_prompt(request.query, contexts, request.history or [])
                yield _sse_event("status", {"stage": "generating", "message": "正在生成回答..."})
                try:
                    async for token in _generate_kb_answer_stream(service, prompt):
                        answer += token
                        yield _sse_event("token", {"delta": token})
                except Exception as exc:
                    logger.warning("知识库流式答案生成失败，改用上下文摘要兜底: %s", exc)
                    answer = build_context_fallback_answer(request.query, contexts)
                    answer_fallback = "answer_generation_failed"
                    yield _sse_event(
                        "error",
                        {"code": "answer_generation_failed", "message": "答案生成服务暂时不可用，已改用召回片段摘要。"},
                    )
                    yield _sse_event("token", {"delta": answer})
            else:
                answer = "当前知识库未找到相关资料。"
                answer_fallback = answer_fallback or "no_result"
                yield _sse_event("token", {"delta": answer})

            answer = answer.strip() or "当前知识库未找到相关资料。"
            yield _sse_event(
                "done",
                {
                    "query": request.query,
                    "database": db_id,
                    "answer": answer,
                    "sources": sources,
                    "total_sources": len(sources),
                    "fallback": answer_fallback,
                    "sources_fallback": context_result.get("fallback"),
                },
            )
        except KeyError:
            yield _sse_event("error", {"code": "database_not_found", "message": f"数据库不存在: {db_id}"})
        except Exception as exc:
            logger.error("知识库流式问答失败: %s", exc)
            yield _sse_event("error", {"code": "kb_chat_stream_failed", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        "vlm": {
            "enabled": config.ENABLE_VLM and bool(config.VLM_API_KEY),
            "provider": "MiniMax (Coding Plan)",
            "endpoint": f"{config.VLM_BASE_URL}/v1/coding_plan/vlm",
        },
        "media": {
            "video_enabled": config.ENABLE_VIDEO_PROCESSING,
            "audio_enabled": config.ENABLE_AUDIO_PROCESSING,
            "mineru_available": bool(config.MINERU_PATH),
            "mineru_path": config.MINERU_PATH,
            "ffmpeg_available": bool(config.FFMPEG_PATH),
            "ffmpeg_path": config.FFMPEG_PATH,
            "whisper_available": bool(config.WHISPER_AVAILABLE),
        },
        "traditional_parser": config.TRADITIONAL_PARSER_DEPENDENCIES,
        "rerank": {
            "enabled": config.ENABLE_RERANK and bool(config.RERANK_API_KEY),
            "provider": "硅基流动",
            "model": config.RERANK_MODEL,
        },
        "query": {
            "default_mode": config.DEFAULT_QUERY_MODE,
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
            "description": item.get("description", ""),
            "status": item.get("status", "active"),
            "engine": item.get("engine", "raganything"),
            "documents_count": len(item.get("documents", [])),
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


@app.post("/db/register")
async def register_database(request: DatabaseRegisterRequest):
    service = _require_service()
    try:
        item = service.registry.register_database(
            request.id,
            name=request.name,
            description=request.description or "",
            engine="traditional",
        )
        return {"status": "success", "database": _database_payload(item)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/db/{db_id}")
async def update_database(db_id: str, request: DatabaseUpdateRequest):
    service = _require_service()
    try:
        engine = _normalize_engine_name(request.engine)
        if engine == "raganything":
            raise HTTPException(status_code=400, detail="不支持将知识库引擎更新为 RAG-Anything")
        item = service.registry.update_database(
            db_id,
            name=request.name,
            description=request.description,
            status=request.status,
            engine=engine,
        )
        return {"status": "success", "database": _database_payload(item)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/db/{db_id}")
async def delete_database(db_id: str):
    service = _require_service()
    try:
        service.registry.delete_database(db_id)
        service.unload_rag(db_id)
        cleanup_dirs = [
            Path(config.RAGANYTHING_STORAGE_ROOT) / "files" / db_id,
            Path(config.RAGANYTHING_STORAGE_ROOT) / db_id,
            Path(config.RAGANYTHING_OUTPUT_ROOT) / db_id,
        ]
        for path in cleanup_dirs:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
        return {"status": "success", "message": f"知识库 '{db_id}' 已删除"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/db/{db_id}/audit")
async def audit_database(db_id: str):
    service = _require_service()
    try:
        from storage_audit import audit_database_storage

        audit = audit_database_storage(service.registry, db_id)
        return {"status": "success", "database": db_id, "audit": audit}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except Exception as e:
        logger.error("知识库存储审计失败 [%s]: %s", db_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/db/{db_id}/documents")
async def list_documents(db_id: str):
    service = _require_service()
    try:
        _reconcile_processing_documents(db_id, service)
        documents = service.registry.list_documents(db_id)
        return {"status": "success", "database": db_id, "documents": documents}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")


@app.post("/db/{db_id}/documents/{sha256}/retry")
async def retry_document(db_id: str, sha256: str, request: RetryDocumentRequest):
    service = _require_service()
    if not service.registry.get_database(db_id):
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    docs = service.registry.list_documents(db_id)
    doc = next((item for item in docs if item.get("sha256") == sha256), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if _is_indexed_traditional_document(doc):
        _finalize_indexed_traditional_document(service, db_id, sha256)
        return {
            "status": "success",
            "message": "传统 RAG 文档已完成索引，无需重新处理",
            "result": {
                "status": "success",
                "database": db_id,
                "document_sha256": sha256,
                "engine": "traditional",
                "chunk_count": int(doc.get("chunk_count") or 0),
            },
        }
    if doc.get("status") == "processing":
        updated_at = str(doc.get("updated_at") or "")
        is_stale = False
        try:
            from datetime import datetime, timezone

            updated = datetime.fromisoformat(updated_at)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            is_stale = (datetime.now(timezone.utc) - updated).total_seconds() > 10 * 60
        except Exception:
            is_stale = False
        if not is_stale:
            raise HTTPException(status_code=409, detail="文档正在处理中，请稍后再试")
        service.registry.update_document_status(db_id, sha256, status="error", error="处理超时，已改为重试。")
        service.registry.update_document_progress(db_id, sha256, stage="interrupted")

    engine = _engine_for_database(db_id)
    if engine is not service:
        file_path = Path(doc["file_path"])
        service.registry.update_document_status(db_id, sha256, status="processing", error="")
        service.registry.update_document_progress(db_id, sha256, stage="indexing")
        try:
            result = await engine.ingest_file(db_id, file_path)
            status = str((result or {}).get("status") or "").strip()
            if not _is_success_ingest_status(status):
                raise RuntimeError(str((result or {}).get("error") or (result or {}).get("message") or "传统 RAG 重试失败"))
            _record_traditional_ingest_result(
                service,
                db_id,
                file_path,
                result or {},
                existing_sha256=sha256,
                source_name=doc.get("file_name") or file_path.name,
            )
            service.registry.update_document_progress(db_id, sha256, stage="done")
            return {"status": "success", "message": "传统 RAG 文档已重新索引", "result": result}
        except Exception as exc:
            service.registry.update_document_status(db_id, sha256, status="error", error=str(exc))
            service.registry.update_document_progress(db_id, sha256, stage="error")
            raise HTTPException(status_code=500, detail=str(exc))

    if request.strategy != "markdown_segments":
        raise HTTPException(status_code=400, detail="仅支持 markdown_segments")

    file_path = Path(doc["file_path"])
    try:
        return await asyncio.to_thread(
            service.recover_from_mineru_markdown,
            db_id,
            file_path,
            sha256,
            request.max_chars,
        )
    except Exception as recovery_exc:
        logger.info(
            "MinerU markdown 分段恢复失败，改用完整重试 [%s/%s]: %s",
            db_id,
            sha256,
            recovery_exc,
        )

    service.registry.update_document_status(db_id, sha256, status="processing", error="")
    service.registry.update_document_progress(db_id, sha256, stage="rag_ingest")
    try:
        result = await asyncio.to_thread(service.ingest_file_sync, db_id, file_path)
        service.registry.update_document_status(db_id, sha256, status="已导入", error="")
        service.registry.update_document_progress(db_id, sha256, stage="done")
        return {"status": "success", "message": "RAG-Anything 文档已重新处理", "result": result}
    except Exception as exc:
        service.registry.update_document_status(db_id, sha256, status="error", error=str(exc))
        service.registry.update_document_progress(db_id, sha256, stage="error")
        raise HTTPException(status_code=500, detail=str(exc))


def _doc_status_path(db_id: str, service: Any) -> Path:
    if hasattr(service, "_db_working_dir"):
        return Path(service._db_working_dir(db_id)) / "kv_store_doc_status.json"
    return Path(config.RAGANYTHING_STORAGE_ROOT) / db_id / "rag_storage" / "kv_store_doc_status.json"


def _load_lightrag_doc_status(db_id: str, service: Any) -> dict[str, Any]:
    status_path = _doc_status_path(db_id, service)
    if not status_path.exists():
        return {}
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 LightRAG 文档状态失败 [%s]: %s", status_path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _status_matches_file(item: dict[str, Any], file_name: str) -> bool:
    candidates = {
        str(item.get("file_path", "")).replace("\\", "/").split("/")[-1],
        str(item.get("source", "")).replace("\\", "/").split("/")[-1],
    }
    return file_name in candidates


def _write_json_file(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 JSON 存储失败 [%s]: %s", path, exc)
        return None


def _value_references_any(value: Any, refs: set[str]) -> bool:
    if not refs:
        return False
    if isinstance(value, str):
        return any(ref and ref in value for ref in refs)
    if isinstance(value, dict):
        return any(_value_references_any(item, refs) for item in value.values())
    if isinstance(value, list):
        return any(_value_references_any(item, refs) for item in value)
    return False


def _prune_chunk_lists(value: Any, chunk_ids: set[str]) -> Any:
    if isinstance(value, dict):
        pruned = {}
        for key, item in value.items():
            if isinstance(item, list) and key in {"chunks", "chunk_ids", "chunks_list", "source_id"}:
                pruned[key] = [chunk for chunk in item if chunk not in chunk_ids]
            else:
                pruned[key] = _prune_chunk_lists(item, chunk_ids)
        return pruned
    if isinstance(value, list):
        return [_prune_chunk_lists(item, chunk_ids) for item in value]
    return value


def _cleanup_dict_store(path: Path, doc_ids: set[str], chunk_ids: set[str], file_refs: set[str]) -> int:
    data = _load_json_file(path)
    if not isinstance(data, dict):
        return 0

    removed = 0
    changed = False
    for key in list(data.keys()):
        value = data[key]
        if key in doc_ids or key in chunk_ids or _value_references_any(value, doc_ids | file_refs):
            data.pop(key, None)
            removed += 1
            changed = True
            continue
        pruned = _prune_chunk_lists(value, chunk_ids)
        if pruned != value:
            data[key] = pruned
            changed = True
            if isinstance(pruned, dict):
                for list_key in ("chunks", "chunk_ids", "chunks_list", "source_id"):
                    if list_key in pruned and pruned[list_key] == []:
                        data.pop(key, None)
                        removed += 1
                        break

    if changed:
        _write_json_file(path, data)
    return removed


def _cleanup_vector_store(path: Path, doc_ids: set[str], chunk_ids: set[str], file_refs: set[str]) -> int:
    data = _load_json_file(path)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return 0

    refs = doc_ids | chunk_ids | file_refs
    before = len(data["data"])
    data["data"] = [
        item
        for item in data["data"]
        if not (
            isinstance(item, dict)
            and (
                str(item.get("__id__", "")) in chunk_ids
                or str(item.get("full_doc_id", "")) in doc_ids
                or _value_references_any(item, refs)
            )
        )
    ]
    removed = before - len(data["data"])
    if removed:
        _write_json_file(path, data)
    return removed


def _cleanup_graph_store(path: Path, refs: set[str]) -> int:
    if not path.exists() or not refs:
        return 0
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        logger.warning("读取 GraphML 存储失败 [%s]: %s", path, exc)
        return 0

    root = tree.getroot()
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}", 1)[0].strip("{")
    ns = {"g": namespace} if namespace else {}
    graph = root.find("g:graph", ns) if namespace else root.find("graph")
    if graph is None:
        return 0

    def element_refs_deleted(element: ET.Element) -> bool:
        return any(ref in "".join(element.itertext()) for ref in refs)

    removed = 0
    removed_nodes: set[str] = set()
    for node in list(graph.findall("g:node", ns) if namespace else graph.findall("node")):
        if element_refs_deleted(node):
            node_id = node.attrib.get("id")
            if node_id:
                removed_nodes.add(node_id)
            graph.remove(node)
            removed += 1

    for edge in list(graph.findall("g:edge", ns) if namespace else graph.findall("edge")):
        if (
            edge.attrib.get("source") in removed_nodes
            or edge.attrib.get("target") in removed_nodes
            or element_refs_deleted(edge)
        ):
            graph.remove(edge)
            removed += 1

    if removed:
        if namespace:
            ET.register_namespace("", namespace)
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return removed


def _cleanup_lightrag_document_residue(db_id: str, service: Any, document: dict[str, Any]) -> dict[str, int]:
    file_name = str(document.get("file_name") or Path(str(document.get("file_path", ""))).name)
    if not file_name:
        return {"doc_status": 0, "chunks": 0, "vectors": 0}

    storage_dir = _doc_status_path(db_id, service).parent
    status_path = storage_dir / "kv_store_doc_status.json"
    doc_status = _load_json_file(status_path)
    if not isinstance(doc_status, dict):
        return {"doc_status": 0, "chunks": 0, "vectors": 0}

    matched_doc_ids: set[str] = set()
    chunk_ids: set[str] = set()
    for doc_id, item in doc_status.items():
        if not isinstance(item, dict) or not _status_matches_file(item, file_name):
            continue
        matched_doc_ids.add(str(doc_id))
        chunk_ids.update(str(chunk) for chunk in item.get("chunks_list", []) if chunk)

    if not matched_doc_ids and not chunk_ids:
        return {"doc_status": 0, "chunks": 0, "vectors": 0}

    file_refs = {file_name, Path(str(document.get("file_path", ""))).name, Path(file_name).stem}
    file_refs = {ref for ref in file_refs if ref}
    removed = {"doc_status": 0, "chunks": 0, "vectors": 0}
    removed["doc_status"] += _cleanup_dict_store(status_path, matched_doc_ids, chunk_ids, file_refs)

    for name in (
        "kv_store_full_docs.json",
        "kv_store_text_chunks.json",
        "kv_store_entity_chunks.json",
        "kv_store_relation_chunks.json",
        "kv_store_parse_cache.json",
    ):
        path = storage_dir / name
        if path.exists():
            removed["chunks"] += _cleanup_dict_store(path, matched_doc_ids, chunk_ids, file_refs)

    for name in ("vdb_chunks.json", "vdb_entities.json", "vdb_relationships.json"):
        path = storage_dir / name
        if path.exists():
            removed["vectors"] += _cleanup_vector_store(path, matched_doc_ids, chunk_ids, file_refs)

    graph_path = storage_dir / "graph_chunk_entity_relation.graphml"
    if graph_path.exists():
        removed["vectors"] += _cleanup_graph_store(graph_path, matched_doc_ids | chunk_ids | file_refs)

    return removed


def _cleanup_mineru_output(db_id: str, service: Any, document: dict[str, Any]) -> int:
    file_name = str(document.get("file_name") or Path(str(document.get("file_path", ""))).name)
    stem = Path(file_name).stem
    if not stem:
        return 0

    if hasattr(service, "_db_output_dir"):
        output_dir = Path(service._db_output_dir(db_id))
    else:
        output_dir = Path(config.RAGANYTHING_OUTPUT_ROOT) / db_id
    if not output_dir.exists():
        return 0

    removed = 0
    output_root = output_dir.resolve()
    for path in output_dir.iterdir():
        if not path.is_dir() or not (path.name == stem or path.name.startswith(f"{stem}_")):
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if output_root not in resolved.parents and resolved != output_root:
            continue
        shutil.rmtree(resolved, ignore_errors=True)
        removed += 1
    return removed


def _latest_status_for_file(doc_status: dict[str, Any], file_name: str) -> tuple[str, dict[str, Any]] | None:
    matches = [
        (doc_id, item)
        for doc_id, item in doc_status.items()
        if isinstance(item, dict) and _status_matches_file(item, file_name)
    ]
    if not matches:
        return None
    matches.sort(key=lambda pair: str(pair[1].get("updated_at") or pair[1].get("created_at") or ""))
    return matches[-1]


def _reconcile_processing_documents(db_id: str, service: Any) -> None:
    documents = service.registry.list_documents(db_id)
    processing_docs = [doc for doc in documents if doc.get("status") == "processing"]
    if not processing_docs:
        return

    for doc in processing_docs:
        if _is_indexed_traditional_document(doc):
            sha256 = str(doc.get("sha256", "")).strip()
            if sha256:
                _finalize_indexed_traditional_document(service, db_id, sha256)

    processing_docs = [doc for doc in service.registry.list_documents(db_id) if doc.get("status") == "processing"]
    if not processing_docs:
        return

    doc_status = _load_lightrag_doc_status(db_id, service)
    if not doc_status:
        return

    for doc in processing_docs:
        file_name = str(doc.get("file_name") or Path(str(doc.get("file_path", ""))).name)
        sha256 = str(doc.get("sha256", "")).strip()
        if not file_name or not sha256:
            continue

        latest = _latest_status_for_file(doc_status, file_name)
        if latest is None:
            continue

        doc_id, item = latest
        status = str(item.get("status", "")).strip().lower()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if status == "processed":
            service.registry.update_document_status(db_id, sha256, status="已导入", error="")
        elif status == "failed" and metadata.get("is_duplicate"):
            original_id = metadata.get("original_doc_id")
            original = doc_status.get(original_id) if original_id else None
            if isinstance(original, dict) and str(original.get("status", "")).lower() == "processed":
                service.registry.update_document_status(db_id, sha256, status="已导入", error="")
            else:
                error = str(item.get("error_msg") or f"重复文档: {doc_id}")
                service.registry.update_document_status(db_id, sha256, status="error", error=error)
        elif status == "failed":
            error = str(item.get("error_msg") or "LightRAG 文档处理失败")
            service.registry.update_document_status(db_id, sha256, status="error", error=error)


def _recover_interrupted_processing_documents(service: Any) -> None:
    """Mark processing documents left by a previous process as interrupted.

    In-memory upload tasks do not survive a service restart. Keep any LightRAG
    terminal status if it exists, then make the remaining registry rows
    user-actionable instead of leaving them permanently stuck in processing.
    """
    if not hasattr(service.registry, "list_databases") or not hasattr(service.registry, "list_documents"):
        return

    for database in service.registry.list_databases():
        db_id = str(database.get("id", "")).strip()
        if not db_id:
            continue
        try:
            _reconcile_processing_documents(db_id, service)
            documents = service.registry.list_documents(db_id)
        except (KeyError, AttributeError):
            continue

        for doc in documents:
            if doc.get("status") != "processing":
                continue
            sha256 = str(doc.get("sha256", "")).strip()
            if not sha256:
                continue
            service.registry.update_document_status(
                db_id,
                sha256,
                status="error",
                error="服务重启后后台导入任务已中断，请删除后重新上传或使用重试。",
            )
            service.registry.update_document_progress(db_id, sha256, stage="interrupted")


@app.delete("/db/{db_id}/documents/{sha256}")
async def delete_document(db_id: str, sha256: str):
    service = _require_service()
    try:
        # 先获取文件路径用于删除物理文件
        docs = service.registry.list_documents(db_id)
        target = next((d for d in docs if d.get("sha256") == sha256), None)
        deleted = service.registry.delete_document(db_id, sha256)
        if not deleted:
            raise HTTPException(status_code=404, detail="文档不存在")
        if target and target.get("file_path"):
            try:
                Path(target["file_path"]).unlink(missing_ok=True)
            except OSError:
                pass
        if target:
            engine = _engine_for_database(db_id)
            if engine is service:
                _cleanup_lightrag_document_residue(db_id, service, target)
                _cleanup_mineru_output(db_id, service, target)
            else:
                try:
                    await engine.delete_document(db_id, sha256)
                except Exception as exc:
                    logger.warning("传统 RAG 文档清理失败 [%s/%s]: %s", db_id, sha256, exc)
        return {"status": "success", "message": "文档已删除"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"数据库不存在: {db_id}")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        payload["query_mode"] = _query_mode()
        return payload
    except Exception as e:
        logger.error(f"多数据库搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/text")
async def ingest_text(request: DocumentIngestRequest):
    _require_service()
    database = _normalize_database_id(request.database) or "default"

    try:
        engine = _engine_for_database(database)
        result = await engine.ingest_text(database, request.text, source=request.source or "manual")
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
            engine = _engine_for_database(db_id)
            result = await engine.ingest_file(db_id, path)
            if engine is not service:
                _record_traditional_ingest_result(service, db_id, path, result)
            return result
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
        engine = _engine_for_database(db_id)
        for file_path in files:
            try:
                result = await engine.ingest_file(db_id, file_path)
                if engine is not service:
                    _record_traditional_ingest_result(service, db_id, file_path, result)
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


@app.post("/ingest/upload")
async def ingest_upload(database: str = Form(...), files: List[UploadFile] = File(...)):
    service = _require_service()
    db_id = _normalize_database_id(database)
    if not db_id:
        raise HTTPException(status_code=400, detail="database 不能为空")

    target_dir = Path(config.RAGANYTHING_STORAGE_ROOT) / "files" / db_id
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        original_name = Path(file.filename or "uploaded_file").name
        stem = Path(original_name).stem or "uploaded_file"
        suffix = Path(original_name).suffix
        candidate = original_name
        counter = 1
        while (target_dir / candidate).exists():
            counter += 1
            candidate = f"{stem}_{counter:03d}{suffix}"
        filename = candidate
        target_path = target_dir / filename

        try:
            target_path.resolve().relative_to(target_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法文件名: {filename}")

        try:
            with open(target_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except Exception as e:
            logger.error(f"文件保存失败: {e}")
            raise HTTPException(status_code=500, detail=f"文件保存失败: {filename}")
        finally:
            file.file.close()

        sha256 = _sha256(target_path)
        db_item = service.registry.get_database(db_id) or {}
        engine_name = database_engine_name(db_item)
        service.registry.register_document(
            db_id,
            file_name=original_name,
            stored_file_name=filename,
            file_path=str(target_path),
            sha256=sha256,
            source=original_name,
            status="processing",
            engine=engine_name,
        )
        service.registry.update_document_progress(db_id, sha256, stage="uploaded")
        saved_files.append((filename, str(target_path), sha256))

    task_id = progress_tracker.create_task(len(saved_files))
    asyncio.create_task(_process_uploaded_files(db_id, saved_files, task_id))

    return {
        "status": "success",
        "database": db_id,
        "task_id": task_id,
        "total": len(saved_files),
        "message": f"{len(saved_files)} 个文件已保存，后台处理中",
    }


async def _process_uploaded_files(db_id: str, files: list, task_id: str):
    service = _require_service()
    engine = _engine_for_database(db_id)
    is_raganything = engine is service
    for filename, filepath, sha256 in files:
        try:
            stage = "rag_ingest" if is_raganything else "indexing"
            message = f"正在 RAG-Anything 解析: {filename}" if is_raganything else f"正在传统 RAG 分块索引: {filename}"
            event_engine = "raganything" if is_raganything else "traditional"
            service.registry.update_document_progress(db_id, sha256, stage=stage)
            progress_tracker.emit(task_id, "parsing", filename, message, engine=event_engine)
            if is_raganything:
                result = await asyncio.to_thread(service.ingest_file_sync, db_id, Path(filepath))
            else:
                result = await engine.ingest_file(db_id, Path(filepath))
                status = str((result or {}).get("status") or "").strip()
                if _is_success_ingest_status(status):
                    _record_traditional_ingest_result(
                        service,
                        db_id,
                        Path(filepath),
                        result or {},
                        existing_sha256=sha256,
                        source_name=filename,
                    )
                else:
                    error = str((result or {}).get("error") or (result or {}).get("message") or "传统 RAG 导入失败")
                    raise RuntimeError(error)
            service.registry.update_document_progress(db_id, sha256, stage="done")
            progress_tracker.emit(task_id, "done", filename, f"{filename} 导入完成")
        except Exception as e:
            logger.error(f"文件导入失败 [{filename}]: {e}")
            service.registry.update_document_status(db_id, sha256, status="error", error=str(e))
            service.registry.update_document_progress(db_id, sha256, stage="error")
            progress_tracker.emit(task_id, "error", filename, f"{filename} 导入失败", error=str(e))
    progress_tracker.finalize(task_id)


@app.get("/ingest/progress/{task_id}")
async def ingest_progress(task_id: str):
    async def event_stream():
        index = 0
        while True:
            events, index, finished = progress_tracker.get_events_since(task_id, index)
            for evt in events:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            if finished:
                yield "data: {\"type\": \"finished\"}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/settings/models")
async def get_model_settings():
    return settings_store.load()


@app.get("/settings/providers")
async def get_model_providers():
    return {"providers": settings_store.providers()}


@app.put("/settings/models")
async def update_model_settings(payload: dict[str, Any]):
    global traditional_service
    try:
        saved = settings_store.save(payload)
        traditional_service = create_traditional_engine()
        return saved
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _endpoint_from_settings(section: dict[str, Any]) -> ModelEndpoint:
    return ModelEndpoint(
        provider=str(section.get("provider") or "openai-compatible"),
        base_url=str(section.get("base_url") or "").rstrip("/"),
        api_key=str(section.get("api_key") or ""),
        model=str(section.get("model") or ""),
        timeout=int(section.get("timeout") or 60),
    )


@app.post("/settings/models/test")
async def test_model_settings(payload: dict[str, Any]):
    target = str(payload.get("target") or "llm").strip().lower()
    runtime = settings_store.runtime(payload)
    try:
        if target == "embedding":
            client = OpenAICompatibleClient(_endpoint_from_settings(runtime["embedding"]))
            vectors = await client.embed(["连接测试"])
            if not vectors or not vectors[0]:
                raise RuntimeError("embedding endpoint returned empty vector")
            return {"status": "success", "target": "embedding", "dimension": len(vectors[0])}
        if target == "rerank":
            client = OpenAICompatibleClient(_endpoint_from_settings(runtime["rerank"]))
            result = await client.rerank("连接测试", ["连接测试文档", "无关文档"], top_n=1)
            return {"status": "success", "target": "rerank", "items": len(result)}
        client = OpenAICompatibleClient(_endpoint_from_settings(runtime["llm"]))
        answer = await client.chat("你是连接测试助手。", "回复 OK")
        return {"status": "success", "target": "llm", "message": answer[:80]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型连接测试失败: {exc}")


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
