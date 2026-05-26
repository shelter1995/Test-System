from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "llm": {
        "provider": "minimax",
        "base_url": "https://api.minimaxi.com/v1",
        "model": "MiniMax-M2.7",
        "timeout": 120,
    },
    "embedding": {
        "provider": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "dimension": 1024,
        "batch_size": 10,
        "batch_interval": 1.0,
        "retry_attempts": 3,
        "retry_base_delay": 30,
        "timeout": 30,
    },
    "rerank": {
        "enabled": True,
        "provider": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-reranker-v2-m3",
        "top_n": 8,
        "timeout": 30,
    },
}

MODEL_CATALOG: dict[str, dict[str, list[str]]] = {
    "llm": {
        "minimax": [
            "MiniMax-M2.7",
            "MiniMax-M2.7-highspeed",
            "MiniMax-M2.5",
            "MiniMax-M2.5-highspeed",
            "MiniMax-M2.1",
            "MiniMax-M2.1-highspeed",
            "MiniMax-M2",
        ],
        "openai-compatible": [],
    },
    "embedding": {
        "siliconflow": [
            "BAAI/bge-m3",
            "Pro/BAAI/bge-m3",
            "BAAI/bge-large-zh-v1.5",
            "BAAI/bge-large-en-v1.5",
            "netease-youdao/bce-embedding-base_v1",
            "Qwen/Qwen3-Embedding-8B",
            "Qwen/Qwen3-Embedding-4B",
            "Qwen/Qwen3-Embedding-0.6B",
        ],
        "openai-compatible": [],
    },
    "rerank": {
        "siliconflow": [
            "BAAI/bge-reranker-v2-m3",
            "Pro/BAAI/bge-reranker-v2-m3",
            "netease-youdao/bce-reranker-base_v1",
            "Qwen/Qwen3-Reranker-8B",
            "Qwen/Qwen3-Reranker-4B",
            "Qwen/Qwen3-Reranker-0.6B",
        ],
        "openai-compatible": [],
    },
}


ENV_KEYS = {
    "llm": ("LLM_API_KEY", "MINIMAX_API_KEY"),
    "embedding": "SILICONFLOW_API_KEY",
    "rerank": "RERANK_API_KEY",
}


def _env_api_key(section: str) -> str:
    env_keys = ENV_KEYS.get(section, "")
    if isinstance(env_keys, str):
        env_keys = (env_keys,) if env_keys else ()
    value = ""
    for env_key in env_keys:
        value = os.getenv(env_key, "")
        if value:
            break
    if section == "rerank" and not value:
        value = os.getenv("SILICONFLOW_API_KEY", "")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _merge_runtime_override(settings: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge form overrides without letting blank API key fields erase saved keys."""
    for key, value in override.items():
        if key == "target":
            continue
        if isinstance(value, dict) and isinstance(settings.get(key), dict):
            target = settings[key]
            for sub_key, sub_value in value.items():
                if sub_key == "api_key" and not str(sub_value or "").strip():
                    continue
                target[sub_key] = sub_value
        else:
            settings[key] = value
    return settings


def _strip_secret_values(settings: dict[str, Any]) -> dict[str, Any]:
    clean = copy.deepcopy(settings)
    for section in ("llm", "embedding", "rerank"):
        item = clean.get(section)
        if not isinstance(item, dict):
            continue
        api_key = str(item.pop("api_key", "") or "")
        item["has_api_key"] = bool(api_key or _env_api_key(section))
    return clean


def _validate_settings(payload: dict[str, Any]) -> None:
    for section in ("llm", "embedding", "rerank"):
        item = payload.get(section)
        if not isinstance(item, dict):
            continue
        if "model" in item and not str(item.get("model") or "").strip():
            raise ValueError(f"{section}.model cannot be empty")
        if "base_url" in item and not str(item.get("base_url") or "").strip():
            raise ValueError(f"{section}.base_url cannot be empty")


class ModelSettingsStore:
    def __init__(self, settings_path: str | Path, local_settings_path: str | Path):
        self.settings_path = Path(settings_path)
        self.local_settings_path = Path(local_settings_path)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_settings_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        return _strip_secret_values(self.runtime())

    def runtime(self, override: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        _deep_merge(settings, _read_json(self.settings_path))
        _deep_merge(settings, _read_json(self.local_settings_path))
        if override:
            _merge_runtime_override(settings, override)
        for section in ENV_KEYS:
            item = settings.setdefault(section, {})
            item.setdefault("api_key", _env_api_key(section))
        return settings

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("settings payload must be an object")
        _validate_settings(payload)

        public_payload = copy.deepcopy(payload)
        local_payload = _read_json(self.local_settings_path)
        persist_keys = bool(public_payload.pop("persist_api_key", False))
        public_payload.pop("target", None)

        for section in ("llm", "embedding", "rerank"):
            item = public_payload.get(section)
            if not isinstance(item, dict):
                continue
            api_key = str(item.pop("api_key", "") or "").strip()
            if api_key and persist_keys:
                local_payload.setdefault(section, {})["api_key"] = api_key

        self.settings_path.write_text(
            json.dumps(public_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if local_payload:
            self.local_settings_path.write_text(
                json.dumps(local_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return self.load()

    def providers(self) -> dict[str, Any]:
        return {
            "llm": ["minimax", "openai-compatible"],
            "embedding": ["siliconflow", "openai-compatible"],
            "rerank": ["siliconflow", "openai-compatible"],
            "models": MODEL_CATALOG,
            "defaults": DEFAULT_SETTINGS,
        }
