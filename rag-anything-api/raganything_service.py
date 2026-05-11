"""
RAG-Anything 服务封装
"""

import asyncio
import hashlib
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import config
from database_registry import DatabaseRegistry


def _normalize_base_url(base_url: str, suffix: str) -> str:
    text = str(base_url or "").rstrip("/")
    if text.endswith(suffix):
        return text
    return text + suffix


def _ensure_raganything_import_path() -> None:
    src = Path(config.RAGANYTHING_SOURCE_DIR)
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    scripts_dir = src / ".venv" / "Scripts"
    if scripts_dir.exists():
        current = os.environ.get("PATH", "")
        scripts_text = str(scripts_dir)
        if scripts_text.lower() not in current.lower():
            os.environ["PATH"] = scripts_text + os.pathsep + current


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_text_filename(source: str, text: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(source or "manual")).strip("._-")
    if not stem:
        stem = "manual"
    stem = stem[:60]
    digest = hashlib.sha256(f"{source}\n{text}".encode("utf-8")).hexdigest()[:12]
    return f"{stem}_{digest}.txt"


class RAGAnythingService:
    def __init__(
        self,
        storage_root: str | Path,
        output_root: str | Path,
        registry: DatabaseRegistry,
        rag_factory: Callable[[str, Path], Any] | None = None,
        query_timeout: float | None = None,
        max_instances: int | None = None,
    ):
        self.storage_root = Path(storage_root)
        self.output_root = Path(output_root)
        self.registry = registry
        self.rag_factory = rag_factory or self._create_rag
        self.query_timeout = float(query_timeout or config.QUERY_ALL_TIMEOUT)
        self.max_instances = max(1, int(max_instances or config.MAX_RAG_INSTANCES))
        self._instances: OrderedDict[str, Any] = OrderedDict()

        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _db_working_dir(self, database_id: str) -> Path:
        return self.storage_root / database_id / "rag_storage"

    def _db_output_dir(self, database_id: str) -> Path:
        return self.output_root / database_id

    def _create_rag(self, database_id: str, working_dir: Path):
        _ensure_raganything_import_path()
        from raganything import RAGAnything, RAGAnythingConfig
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        if config.HF_ENDPOINT:
            os.environ["HF_ENDPOINT"] = config.HF_ENDPOINT

        llm_base = _normalize_base_url(config.MINIMAX_BASE_URL, "/v1")
        embedding_base = _normalize_base_url(config.SILICONFLOW_BASE_URL, "/v1")

        async def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
            kwargs.pop("keyword_extraction", None)
            response = await openai_complete_if_cache(
                config.MINIMAX_MODEL_M27,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                api_key=config.MINIMAX_API_KEY,
                base_url=llm_base,
                **kwargs,
            )
            if isinstance(response, str):
                response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            return response

        async def embedding_func_async(texts, **kwargs):
            return await openai_embed.func(
                texts=texts,
                model=config.SILICONFLOW_MODEL,
                base_url=embedding_base,
                api_key=config.SILICONFLOW_API_KEY,
                max_token_size=config.EMBEDDING_MAX_TOKENS,
            )

        embedding_func = EmbeddingFunc(
            embedding_dim=config.EMBEDDING_DIM,
            max_token_size=config.EMBEDDING_MAX_TOKENS,
            func=embedding_func_async,
        )

        rag_config = RAGAnythingConfig(
            working_dir=str(working_dir),
            parser_output_dir=str(self._db_output_dir(database_id)),
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

    def database_exists(self, database_id: str) -> bool:
        database_id = str(database_id).strip()
        if not database_id:
            return False
        return self.registry.get_database(database_id) is not None

    def get_rag(self, database_id: str, create_if_missing: bool = False):
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database must not be empty")

        if not create_if_missing and not self.database_exists(database_id):
            raise KeyError(f"database not found: {database_id}")

        if database_id in self._instances:
            self._instances.move_to_end(database_id)
            return self._instances[database_id]

        working_dir = self._db_working_dir(database_id)
        working_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self._db_output_dir(database_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._instances[database_id] = self.rag_factory(database_id, working_dir)
        self._instances.move_to_end(database_id)
        while len(self._instances) > self.max_instances:
            self._instances.popitem(last=False)
        self.registry.register_database(
            database_id,
            working_dir=str(working_dir),
            output_dir=str(output_dir),
        )
        return self._instances[database_id]

    def unload_rag(self, database_id: str) -> bool:
        database_id = str(database_id).strip()
        if database_id not in self._instances:
            return False
        self._instances.pop(database_id, None)
        return True

    async def query(self, database_id: str, query: str, mode: str = "hybrid", n_results: int = 10,
                    enable_rerank: Optional[bool] = None) -> dict[str, Any]:
        rag = self.get_rag(database_id, create_if_missing=False)
        init_result = await rag._ensure_lightrag_initialized()
        if not init_result or not init_result.get("success"):
            raise RuntimeError(f"RAG 引擎初始化失败: {(init_result or {}).get('error', 'unknown')}")

        aquery_kwargs = {"mode": mode}
        if enable_rerank is not None:
            aquery_kwargs["enable_rerank"] = enable_rerank
        answer = await rag.aquery(query, **aquery_kwargs)
        db = self.registry.get_database(database_id) or {}
        sources = [
            item.get("file_name")
            for item in db.get("documents", [])
            if item.get("file_name")
        ]
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
            ][: max(1, n_results)],
            "total_found": 1,
        }

    async def query_all(self, query: str, mode: str = "hybrid", n_results: int = 10,
                        enable_rerank: Optional[bool] = None) -> dict[str, Any]:
        async def query_one(db_id: str):
            try:
                return await asyncio.wait_for(
                    self.query(db_id, query, mode=mode, n_results=1, enable_rerank=enable_rerank),
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

    async def ingest_file(self, database_id: str, file_path: str | Path, source: str | None = None) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(str(path))

        rag = self.get_rag(database_id, create_if_missing=True)
        output_dir = self._db_output_dir(database_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        await rag.process_document_complete(
            file_path=str(path),
            output_dir=str(output_dir),
            parse_method=config.PARSE_METHOD,
            display_stats=True,
            backend=config.MINERU_BACKEND,
        )

        self.registry.register_document(
            database_id,
            file_name=path.name,
            file_path=str(path),
            sha256=_sha256(path),
            source=source or path.name,
        )
        return {
            "status": "success",
            "database": database_id,
            "file": path.name,
            "message": "文档已通过 RAG-Anything 导入知识库",
        }

    def ingest_file_sync(self, database_id: str, file_path: str | Path, source: str | None = None) -> dict[str, Any]:
        """同步包装 ingest_file，供 asyncio.to_thread 后台调用。"""
        return asyncio.run(self.ingest_file(database_id, file_path, source))

    async def ingest_text(self, database_id: str, text: str, source: str = "manual") -> dict[str, Any]:
        content = str(text or "").strip()
        if not content:
            raise ValueError("text must not be empty")

        source_text = str(source or "manual").strip() or "manual"
        text_dir = self.storage_root / str(database_id).strip() / "text_ingest"
        text_dir.mkdir(parents=True, exist_ok=True)
        text_file = text_dir / _safe_text_filename(source_text, content)
        text_file.write_text(f"[来源: {source_text}]\n{content}\n", encoding="utf-8")

        result = await self.ingest_file(database_id, text_file, source=source_text)
        result["source"] = source_text
        return result
