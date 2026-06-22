"""Resolved locations for mutable tutor runtime data."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class RuntimePaths:
    tutor_data: Path
    generation_output: Path
    logs: Path


def _absolute_override(
    name: str,
    fallback: Path,
    environ: Mapping[str, str],
) -> Path:
    raw_value = environ.get(name, "").strip()
    if not raw_value:
        return fallback.resolve()
    value = Path(raw_value)
    if not value.is_absolute():
        raise ValueError(f"{name} must be an absolute path: {raw_value}")
    return value.resolve()


def resolve_runtime_paths(
    environ: Mapping[str, str] | None = None,
    source_root: str | Path | None = None,
) -> RuntimePaths:
    values = os.environ if environ is None else environ
    root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parent.parent
    return RuntimePaths(
        tutor_data=_absolute_override(
            "TEST_SYSTEM_TUTOR_DATA_DIR",
            root / "ai-tutor-system" / "tutor_data",
            values,
        ),
        generation_output=_absolute_override(
            "TEST_SYSTEM_GENERATION_OUTPUT_DIR",
            root / "generation_output",
            values,
        ),
        logs=_absolute_override(
            "TEST_SYSTEM_LOG_DIR",
            root / "runtime" / "logs",
            values,
        ),
    )


def load_runtime_env() -> Path:
    """Load the tutor dotenv selected for this checkout without overriding OS values."""
    source_root = Path(__file__).resolve().parent.parent
    data_dir_value = os.getenv("TEST_SYSTEM_DATA_DIR", "").strip()
    data_dir = Path(data_dir_value) if data_dir_value else None
    if data_dir is not None and data_dir.is_absolute():
        env_path = (data_dir / "config" / "tutor.env").resolve()
    else:
        env_path = (source_root / "ai-tutor-system" / ".env").resolve()
    if env_path.exists():
        load_dotenv(env_path, override=False)
    return env_path


@lru_cache(maxsize=1)
def get_runtime_paths() -> RuntimePaths:
    load_runtime_env()
    return resolve_runtime_paths()
