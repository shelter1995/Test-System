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
from typing import Any, Callable, Optional

import httpx

import config
from raganything import RAGAnything, RAGAnythingConfig
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

from database_registry import DatabaseRegistry
from markdown_splitter import split_markdown_text, write_markdown_segments

logger = logging.getLogger(__name__)

ZH_GENERIC_TERMS = {
    "如何",
    "怎么",
    "怎样",
    "哪些",
    "什么",
    "为何",
    "为什么",
    "是否",
    "可以",
    "需要",
    "时候",
    "一下",
    "一个",
    "这个",
    "那个",
    "做法",
    "方法",
    "步骤",
    "流程",
    "内容",
    "相关",
}


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


def _query_terms(query: str) -> list[str]:
    terms = []
    for token in re.findall(r"[0-9A-Za-z]+|[\u4e00-\u9fff]+", str(query or "").lower()):
        if len(token) >= 2:
            terms.append(token)
            if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 4:
                terms.extend(token[i : i + 2] for i in range(len(token) - 1))
    seen = set()
    result = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            result.append(term)
    return result


def _score_text(text: str, terms: list[str]) -> int:
    haystack = str(text or "").lower()
    if not haystack or not terms:
        return 0

    content_terms = [term for term in terms if term not in ZH_GENERIC_TERMS]
    if content_terms and not any(term in haystack for term in content_terms):
        return 0

    raw_score = 0.0
    matched_terms = 0
    capped_total = 0.0
    for term in terms:
        count = haystack.count(term)
        if count:
            matched_terms += 1
            term_len = len(term)
            is_zh = bool(re.fullmatch(r"[\u4e00-\u9fff]+", term))

            if is_zh and term in ZH_GENERIC_TERMS:
                weight = 0.25
            elif term_len >= 6:
                weight = 2.4
            elif term_len >= 4:
                weight = 1.9
            elif term_len == 3:
                weight = 1.5
            else:
                weight = 1.0

            # 高频词在超长文档里会天然放大，做上限截断避免“长文噪声优势”。
            capped_count = min(count, 10)
            capped_total += capped_count
            raw_score += capped_count * max(1, term_len) * weight

    if raw_score <= 0:
        return 0

    coverage = matched_terms / max(1, len(terms))
    length_penalty = 1.0 + (len(haystack) / 2800.0)
    coverage_bonus = 0.55 + coverage
    concentration_bonus = 1.0 + (capped_total / max(1.0, len(haystack) / 120.0))

    final_score = raw_score * coverage_bonus * concentration_bonus / length_penalty
    return int(final_score)


def _trim_snippet(text: str, terms: list[str], max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= max_chars:
        return clean
    lower = clean.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(clean), start + max_chars)
    return clean[start:end].strip()


def _split_local_markdown(text: str, max_chars: int = 1800) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return []

    sections: list[str] = []
    current: list[str] = []
    for line in clean.splitlines():
        if line.lstrip().startswith("#") and current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)
            current = [line]
        else:
            current.append(line)
    if current:
        section = "\n".join(current).strip()
        if section:
            sections.append(section)

    if not sections:
        sections = [clean]

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        start = 0
        while start < len(section):
            chunks.append(section[start : start + max_chars].strip())
            start += max_chars
    return [chunk for chunk in chunks if chunk]


def _is_no_context_response(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return True
    markers = (
        "[no-context]",
        "no relevant document chunks found",
        "no relevant",
        "未找到相关",
        "没有找到相关",
    )
    return any(marker in normalized for marker in markers)


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
        self._instance_loop_ids: dict[str, int | None] = {}

        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def _db_working_dir(self, database_id: str) -> Path:
        return self.storage_root / database_id / "rag_storage"

    def _db_output_dir(self, database_id: str) -> Path:
        return self.output_root / database_id

    def _registered_source_stems(self, database_id: str) -> set[str]:
        database = self.registry.get_database(database_id) or {}
        stems: set[str] = set()
        for doc in database.get("documents", []):
            for key in ("file_name", "source", "stored_file_name"):
                value = str(doc.get(key) or "").strip()
                if not value:
                    continue
                path = Path(value)
                stems.add(path.name)
                stems.add(path.stem)
        return {stem for stem in stems if stem}

    def _matches_registered_source(self, database_id: str, source: str) -> bool:
        registered = self._registered_source_stems(database_id)
        if not registered:
            return True

        candidate = Path(str(source or "")).name.strip()
        if not candidate:
            return False
        candidate_stem = Path(candidate).stem
        for registered_name in registered:
            registered_stem = Path(registered_name).stem
            if candidate == registered_name or candidate_stem == registered_stem:
                return True
            if registered_stem and candidate_stem.startswith(f"{registered_stem}_part_"):
                return True
            if registered_stem and candidate_stem.startswith(registered_stem):
                return True
        return False

    def _current_loop_id(self) -> int | None:
        try:
            return id(asyncio.get_running_loop())
        except RuntimeError:
            return None

    async def _call_llm(self, prompt: str, system_prompt: str | None = None, history_messages: list | None = None, **kwargs) -> str:
        llm_base = _normalize_base_url(config.MINIMAX_BASE_URL, "/v1")
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

    def _create_rag(self, database_id: str, working_dir: Path):
        if config.HF_ENDPOINT:
            os.environ["HF_ENDPOINT"] = config.HF_ENDPOINT

        embedding_base = _normalize_base_url(config.SILICONFLOW_BASE_URL, "/v1")

        async def llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
            return await self._call_llm(
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                **kwargs,
            )

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
            enable_video_processing=config.ENABLE_VIDEO_PROCESSING,
            enable_audio_processing=config.ENABLE_AUDIO_PROCESSING,
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

        loop_id = self._current_loop_id()
        if (
            database_id in self._instances
            and self._instance_loop_ids.get(database_id) == loop_id
        ):
            self._instances.move_to_end(database_id)
            return self._instances[database_id]
        if database_id in self._instances:
            self._instances.pop(database_id, None)
            self._instance_loop_ids.pop(database_id, None)

        working_dir = self._db_working_dir(database_id)
        working_dir.mkdir(parents=True, exist_ok=True)
        output_dir = self._db_output_dir(database_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._instances[database_id] = self.rag_factory(database_id, working_dir)
        self._instance_loop_ids[database_id] = loop_id
        self._instances.move_to_end(database_id)
        while len(self._instances) > self.max_instances:
            evicted_db_id, _ = self._instances.popitem(last=False)
            self._instance_loop_ids.pop(evicted_db_id, None)
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
        self._instance_loop_ids.pop(database_id, None)
        return True

    def _load_local_items(self, database_id: str) -> list[dict[str, Any]]:
        items = []
        seen = set()

        def add_item(text: str, source: str, kind: str):
            text = str(text or "").strip()
            source = str(source or "").strip()
            if not text or not self._matches_registered_source(database_id, source):
                return
            key = (source, text[:200])
            if key in seen:
                return
            seen.add(key)
            items.append(
                {
                    "text": text,
                    "metadata": {
                        "source": source,
                        "database": database_id,
                        "mode": "local_fallback",
                        "kind": kind,
                    },
                    "score": 0,
                }
            )

        working_dir = self._db_working_dir(database_id)
        for filename, field, kind in (
            ("kv_store_text_chunks.json", "content", "chunk"),
            ("kv_store_full_docs.json", "content", "document"),
        ):
            path = working_dir / filename
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        for value in data.values():
                            if isinstance(value, dict):
                                add_item(
                                    value.get(field, ""),
                                    value.get("file_path") or filename,
                                    kind,
                                )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("Local fallback failed reading %s: %s", path, exc)

        output_dir = self._db_output_dir(database_id)
        if output_dir.exists():
            for path in output_dir.rglob("*.md"):
                try:
                    for chunk in _split_local_markdown(path.read_text(encoding="utf-8")):
                        add_item(chunk, path.name, "mineru_markdown")
                except OSError as exc:
                    logger.warning("Local fallback failed reading %s: %s", path, exc)

        db = self.registry.get_database(database_id) or {}
        for doc in db.get("documents", []):
            path = Path(str(doc.get("file_path") or ""))
            if path.suffix.lower() in {".txt", ".md"} and path.exists():
                try:
                    add_item(path.read_text(encoding="utf-8"), doc.get("file_name") or path.name, "source_file")
                except OSError as exc:
                    logger.warning("Local fallback failed reading %s: %s", path, exc)

        return items

    def _local_search(self, database_id: str, query: str, n_results: int = 10, max_chars: int = 1200) -> dict[str, Any]:
        terms = _query_terms(query)
        ranked = []
        for item in self._load_local_items(database_id):
            score = _score_text(item["text"], terms)
            if score > 0 or not terms:
                copy = dict(item)
                copy["metadata"] = dict(item.get("metadata", {}))
                copy["metadata"]["fallback_reason"] = "rag_query_unavailable"
                copy["metadata"].setdefault("engine", "raganything")
                copy["score"] = float(score or 1)
                copy["text"] = _trim_snippet(item["text"], terms, max_chars)
                ranked.append(copy)

        ranked.sort(key=lambda item: item.get("score", 0), reverse=True)
        results = ranked[: max(1, n_results)]
        return {
            "query": query,
            "database": database_id,
            "results": results,
            "contexts": results,
            "total_found": len(results),
            "fallback": "local_text",
        }

    async def query(self, database_id: str, query: str, mode: str = "hybrid", n_results: int = 10,
                    enable_rerank: Optional[bool] = None,
                    vlm_enhanced: Optional[bool] = None) -> dict[str, Any]:
        rag = self.get_rag(database_id, create_if_missing=False)
        init_result = await rag._ensure_lightrag_initialized()
        if not init_result or not init_result.get("success"):
            logger.warning(
                "RAG query initialization failed for database=%s query=%r: %s; using local fallback",
                database_id,
                query,
                (init_result or {}).get("error", "unknown"),
            )
            return self._local_search(database_id, query, n_results=n_results)

        aquery_kwargs = {"mode": mode}
        if enable_rerank is not None:
            aquery_kwargs["enable_rerank"] = enable_rerank
        if vlm_enhanced is not None:
            aquery_kwargs["vlm_enhanced"] = vlm_enhanced
        try:
            answer = await asyncio.wait_for(
                rag.aquery(query, **aquery_kwargs),
                timeout=config.RAG_QUERY_TIMEOUT,
            )
        except Exception as exc:
            logger.warning(
                "RAG query failed or timed out for database=%s query=%r: %s; using local fallback",
                database_id,
                query,
                exc,
            )
            return self._local_search(database_id, query, n_results=n_results)
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
        if getattr(config, "CONTEXT_LOCAL_FIRST", True):
            result = self._local_search(
                database_id,
                query,
                n_results=5,
                max_chars=max(500, max_chars // 2),
            )
            contexts = result.get("contexts", [])
            if contexts:
                return {
                    "query": query,
                    "database": database_id,
                    "contexts": contexts,
                    "total_found": len(contexts),
                    "fallback": "local_text",
                }

        rag = self.get_rag(database_id, create_if_missing=False)
        init_result = await rag._ensure_lightrag_initialized()
        if not init_result or not init_result.get("success"):
            logger.warning(
                "RAG context initialization failed for database=%s query=%r: %s; using local fallback",
                database_id,
                query,
                (init_result or {}).get("error", "unknown"),
            )
            result = self._local_search(
                database_id,
                query,
                n_results=5,
                max_chars=max(500, max_chars // 2),
            )
            contexts = result.get("contexts", [])
            return {
                "query": query,
                "database": database_id,
                "contexts": contexts,
                "total_found": len(contexts),
                "fallback": "local_text",
                "fallback_reason": "rag_init_failed",
            }

        try:
            context = await asyncio.wait_for(
                rag.aquery(
                    query,
                    mode=mode,
                    only_need_context=True,
                    vlm_enhanced=False,
                ),
                timeout=config.RAG_QUERY_TIMEOUT,
            )
        except Exception as exc:
            logger.warning(
                "RAG context query failed or timed out for database=%s query=%r: %s; using local fallback",
                database_id,
                query,
                exc,
            )
            result = self._local_search(
                database_id,
                query,
                n_results=5,
                max_chars=max(500, max_chars // 2),
            )
            contexts = result.get("contexts", [])
            return {
                "query": query,
                "database": database_id,
                "contexts": contexts,
                "total_found": len(contexts),
                "fallback": "local_text",
            }
        text = str(context).strip()
        if _is_no_context_response(text):
            result = self._local_search(
                database_id,
                query,
                n_results=5,
                max_chars=max(500, max_chars // 2),
            )
            contexts = result.get("contexts", [])
            return {
                "query": query,
                "database": database_id,
                "contexts": contexts,
                "total_found": len(contexts),
                "fallback": "local_text" if contexts else "no_context",
            }
        if max_chars > 0:
            text = text[:max_chars]

        contexts = []
        if text:
            contexts.append(
                {
                    "text": text,
                    "metadata": {"source": database_id, "database": database_id, "mode": mode, "engine": "raganything"},
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
            stored_file_name=path.name,
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

    def recover_from_mineru_markdown(
        self,
        database_id: str,
        file_path: str | Path,
        sha256: str,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        source_path = Path(file_path)
        output_dir = self._db_output_dir(database_id)
        if not output_dir.exists():
            raise FileNotFoundError(f"MinerU output directory not found: {output_dir}")

        stem = source_path.stem
        candidates = [
            path for path in output_dir.iterdir()
            if path.is_dir() and path.name.startswith(stem)
        ]
        if not candidates:
            raise FileNotFoundError(f"MinerU output not found for: {source_path.name}")

        sorted_candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
        markdown_path: Path | None = None
        for candidate in sorted_candidates:
            direct = candidate / f"{stem}.md"
            if direct.exists():
                markdown_path = direct
                break
            nested_matches = list(candidate.rglob(f"{stem}.md"))
            if nested_matches:
                markdown_path = max(nested_matches, key=lambda p: p.stat().st_mtime)
                break
        if markdown_path is None:
            raise FileNotFoundError(
                f"MinerU markdown not found for: {source_path.name} under {output_dir}"
            )

        text = markdown_path.read_text(encoding="utf-8")
        segments = split_markdown_text(text, max_chars=max_chars)
        if not segments:
            raise ValueError("MinerU markdown is empty")

        segment_dir = self.storage_root / str(database_id).strip() / "segments" / str(sha256).strip()
        segment_files = write_markdown_segments(segments, segment_dir, source_stem=stem)

        done = 0
        failed = 0
        partial_errors: list[str] = []
        total = len(segment_files)

        self.registry.update_document_progress(
            database_id,
            sha256,
            stage="graph_enrichment",
            segments_total=total,
            segments_done=done,
            segments_failed=failed,
            partial_errors=partial_errors,
        )

        for segment in segment_files:
            try:
                self.ingest_file_sync(database_id, segment, source=source_path.name)
                # 分段文件是中间产物，不应作为独立文档出现在知识库清单中。
                self.registry.delete_document(database_id, _sha256(segment))
                done += 1
            except Exception as exc:
                failed += 1
                partial_errors.append(str(exc))
            self.registry.update_document_progress(
                database_id,
                sha256,
                stage="graph_enrichment",
                segments_total=total,
                segments_done=done,
                segments_failed=failed,
                partial_errors=partial_errors,
            )

        if done == total:
            status = "已导入"
            error = ""
        elif done > 0:
            status = "partial_success"
            error = f"{failed} segment failed"
        else:
            status = "error"
            error = f"{failed} segment failed"

        self.registry.update_document_status(database_id, sha256, status=status, error=error)
        return {
            "status": status,
            "database": database_id,
            "file": source_path.name,
            "segments_total": total,
            "segments_done": done,
            "segments_failed": failed,
            "partial_errors": partial_errors,
            "error": error,
        }

    async def generate_answer(self, prompt: str) -> str:
        response = await self._call_llm(
            prompt,
            system_prompt="你是严谨的中文知识库问答助手。",
            history_messages=[],
        )
        return str(response or "").strip()

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
