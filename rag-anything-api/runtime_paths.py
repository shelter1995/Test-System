"""Runtime path helpers for mutable RAG service data."""

import os
from collections.abc import Mapping
from pathlib import Path


def absolute_env_path(
    name: str,
    fallback: str | Path,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return an absolute resolved override, or the resolved fallback."""
    values = os.environ if environ is None else environ
    raw_value = values.get(name, "").strip()
    if not raw_value:
        return Path(fallback).resolve()

    override = Path(raw_value)
    if not override.is_absolute():
        raise ValueError(f"{name} must be an absolute path: {raw_value}")
    return override.resolve()
