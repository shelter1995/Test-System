"""
RAG-Anything 服务封装
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import httpx

from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

import config
from database_registry import DatabaseRegistry

logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: str, suffix: str) -> str:
    text = str(base_url or "").rstrip("/")
    if text.endswith(suffix):
        return text
    return text + suffix


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

        # 构建 LightRAG 额外参数
        lightrag_kwargs = {
            "chunk_token_size": config.CHUNK_SIZE,
            "chunk_overlap_token_size": config.CHUNK_OVERLAP_SIZE,
        }

        # 如果启用了 rerank，创建 rerank 函数
        rerank_func = self._build_rerank_func()
        if rerank_func:
            lightrag_kwargs["rerank_model_func"] = rerank_func

        # 如果启用了 VLM，创建 vision_model_func
        vision_func = self._build_vision_func()

        return RAGAnything(
            config=rag_config,
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            vision_model_func=vision_func,
            lightrag_kwargs=lightrag_kwargs,
        )

    # ------------------------------------------------------------------
    # VLM 图片理解函数（MiniMax Coding Plan 专用接口）
    # POST /v1/coding_plan/vlm  {prompt, image_url} → {content}
    # ------------------------------------------------------------------
    def _build_vision_func(self):
        """创建 MiniMax Coding Plan VLM 函数，支持三种调用模式：
        1) func(prompt, system_prompt=...)            → 纯文本，走标准 chat
        2) func("", messages=[{...}])                → 多模态消息，提取首张图片 + 文字
        3) func(prompt, image_data=base64, system_prompt=...) → 单图分析
        """
        if not config.ENABLE_VLM or not config.VLM_API_KEY:
            return None

        api_key = config.VLM_API_KEY
        base_url = config.VLM_BASE_URL
        timeout = config.LLM_TIMEOUT_M27

        async def _call_coding_plan_vlm(client: httpx.AsyncClient, prompt_text: str,
                                        image_data_url: str) -> str:
            """调用 MiniMax Coding Plan VLM 接口。"""
            resp = await client.post(
                f"{base_url}/v1/coding_plan/vlm",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": prompt_text,
                    "image_url": image_data_url,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            base_r = data.get("base_resp", {})
            if base_r.get("status_code", 0) != 0:
                raise RuntimeError(
                    f"MiniMax VLM 错误 [{base_r.get('status_code')}]: "
                    f"{base_r.get('status_msg', '未知')}"
                )
            return data.get("content", "")

        def _extract_from_messages(msgs: list):
            """从 RAGAnything 构建的 messages 中提取文本和首张图片。"""
            all_text = []
            first_image = None
            for msg in msgs:
                content = msg.get("content", "")
                if isinstance(content, str):
                    if msg.get("role") == "system":
                        all_text.insert(0, content)
                    else:
                        all_text.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            all_text.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            url = part.get("image_url", {}).get("url", "")
                            if url and first_image is None:
                                first_image = url
            return "\n".join(all_text), first_image

        async def vision_model_func(prompt=None, system_prompt=None, messages=None,
                                     image_data=None, **kwargs):
            async with httpx.AsyncClient(timeout=timeout) as client:
                # 模式 3：单图分析（Processor 调用）
                if image_data:
                    return await _call_coding_plan_vlm(
                        client,
                        prompt or "请描述这张图片",
                        f"data:image/jpeg;base64,{image_data}",
                    )

                # 模式 2：多模态消息（VLM 增强查询调用）
                if messages:
                    text, img = _extract_from_messages(messages)
                    if img:
                        return await _call_coding_plan_vlm(client, text, img)
                    # 没有图片则退回纯文本
                    prompt = text

                # 模式 1：纯文本 — 走标准 chat completion
                final_prompt = prompt or ""
                if system_prompt:
                    final_prompt = f"{system_prompt}\n\n{final_prompt}"
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "MiniMax-M2.7",
                        "messages": [{"role": "user", "content": final_prompt}],
                        "temperature": 0.3,
                        "max_tokens": 4096,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    return choices[0]["message"].get("content", "")
                if choices and "messages" in choices[0]:
                    return choices[0]["messages"][-1].get("text", "")
                return ""

        logger.info("VLM 已启用 (MiniMax Coding Plan): endpoint=%s/v1/coding_plan/vlm", base_url)
        return vision_model_func

    # ------------------------------------------------------------------
    # Rerank 重排序函数（硅基流动）
    # ------------------------------------------------------------------
    def _build_rerank_func(self):
        """创建硅基流动 Rerank 函数。"""
        if not config.ENABLE_RERANK or not config.RERANK_API_KEY:
            return None

        api_key = config.RERANK_API_KEY
        base_url = config.RERANK_BASE_URL
        model = config.RERANK_MODEL
        timeout = config.EMBEDDING_TIMEOUT

        async def rerank_model_func(query: str, documents: list, top_k: int = 5):
            if not documents:
                return []
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base_url}/rerank",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "query": query,
                        "documents": documents,
                        "top_n": min(top_k, len(documents)),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", [])

        logger.info(
            "Rerank 已启用: model=%s base_url=%s", model, base_url,
        )
        return rerank_model_func

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
                    enable_rerank: Optional[bool] = None,
                    vlm_enhanced: Optional[bool] = None) -> dict[str, Any]:
        rag = self.get_rag(database_id, create_if_missing=False)
        init_result = await rag._ensure_lightrag_initialized()
        if not init_result or not init_result.get("success"):
            raise RuntimeError(f"RAG 引擎初始化失败: {(init_result or {}).get('error', 'unknown')}")

        aquery_kwargs = {"mode": mode}
        if enable_rerank is not None:
            aquery_kwargs["enable_rerank"] = enable_rerank
        if vlm_enhanced is not None:
            aquery_kwargs["vlm_enhanced"] = vlm_enhanced
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
                        "source": database_id,
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
                    "metadata": {"source": database_id, "database": database_id, "mode": mode},
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
