from __future__ import annotations

from typing import Any

import config
from rag_engines.traditional.engine import TraditionalRAGEngine
from rag_engines.traditional.model_clients import ModelEndpoint, OpenAICompatibleClient


def _embedding_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        ModelEndpoint(
            provider="siliconflow",
            base_url=config._normalize_base_url(config.SILICONFLOW_BASE_URL, "/v1"),
            api_key=config.SILICONFLOW_API_KEY,
            model=config.SILICONFLOW_MODEL,
            timeout=config.EMBEDDING_TIMEOUT,
        )
    )


def _rerank_client() -> OpenAICompatibleClient | None:
    if not config.ENABLE_RERANK or not config.RERANK_API_KEY:
        return None
    return OpenAICompatibleClient(
        ModelEndpoint(
            provider="siliconflow",
            base_url=config.RERANK_BASE_URL,
            api_key=config.RERANK_API_KEY,
            model=config.RERANK_MODEL,
            timeout=config.EMBEDDING_TIMEOUT,
        )
    )


def create_traditional_engine() -> TraditionalRAGEngine:
    return TraditionalRAGEngine(
        storage_root=config.TRADITIONAL_RAG_STORAGE_ROOT,
        embedding_client=_embedding_client(),
        rerank_client=_rerank_client(),
        chunk_size=config.TRADITIONAL_CHUNK_SIZE,
        chunk_overlap=config.TRADITIONAL_CHUNK_OVERLAP,
    )


def database_engine_name(database: dict[str, Any] | None) -> str:
    name = str((database or {}).get("engine") or config.DEFAULT_RAG_ENGINE or "traditional").strip().lower()
    return name if name in {"traditional", "raganything"} else "traditional"
