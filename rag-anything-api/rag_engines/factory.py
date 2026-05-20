from __future__ import annotations

from typing import Any

import config
from model_settings import ModelSettingsStore
from rag_engines.traditional.engine import TraditionalRAGEngine
from rag_engines.traditional.model_clients import ModelEndpoint, OpenAICompatibleClient


def _runtime_settings() -> dict[str, Any]:
    store = ModelSettingsStore(
        config.STORAGE_ROOT / "model_settings.json",
        config.STORAGE_ROOT / "model_settings.local.json",
    )
    return store.runtime()


def _normalize_provider_base_url(provider: str, base_url: str) -> str:
    text = str(base_url or "").rstrip("/")
    if provider in {"siliconflow", "minimax"} and not text.endswith("/v1"):
        return f"{text}/v1"
    return text


def _endpoint(section: dict[str, Any], default_provider: str, default_model: str, timeout: int) -> ModelEndpoint:
    provider = str(section.get("provider") or default_provider).strip().lower()
    return ModelEndpoint(
        provider=provider,
        base_url=_normalize_provider_base_url(provider, str(section.get("base_url") or "")),
        api_key=str(section.get("api_key") or ""),
        model=str(section.get("model") or default_model),
        timeout=int(section.get("timeout") or timeout),
        batch_size=int(section.get("batch_size") or config.EMBEDDING_BATCH_SIZE),
        batch_interval=float(section.get("batch_interval") or config.EMBEDDING_BATCH_INTERVAL),
        retry_attempts=int(section.get("retry_attempts") or config.EMBEDDING_RETRY_ATTEMPTS),
        retry_base_delay=float(section.get("retry_base_delay") or config.EMBEDDING_RETRY_BASE_DELAY),
    )


def _embedding_client(settings: dict[str, Any]) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        _endpoint(
            settings.get("embedding") or {},
            default_provider="siliconflow",
            default_model=config.SILICONFLOW_MODEL,
            timeout=config.EMBEDDING_TIMEOUT,
        )
    )


def _rerank_client(settings: dict[str, Any]) -> OpenAICompatibleClient | None:
    section = settings.get("rerank") or {}
    enabled = bool(section.get("enabled", config.ENABLE_RERANK))
    if not enabled:
        return None
    endpoint = _endpoint(
        section,
        default_provider="siliconflow",
        default_model=config.RERANK_MODEL,
        timeout=config.EMBEDDING_TIMEOUT,
    )
    if not endpoint.api_key:
        return None
    return OpenAICompatibleClient(endpoint)


def create_traditional_engine() -> TraditionalRAGEngine:
    settings = _runtime_settings()
    return TraditionalRAGEngine(
        storage_root=config.TRADITIONAL_RAG_STORAGE_ROOT,
        embedding_client=_embedding_client(settings),
        rerank_client=_rerank_client(settings),
        chunk_size=config.TRADITIONAL_CHUNK_SIZE,
        chunk_overlap=config.TRADITIONAL_CHUNK_OVERLAP,
    )


def database_engine_name(database: dict[str, Any] | None) -> str:
    name = str((database or {}).get("engine") or config.DEFAULT_RAG_ENGINE or "traditional").strip().lower()
    return name if name in {"traditional", "raganything"} else "traditional"
