"""Resolved locations for mutable tutor runtime data."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


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


def get_runtime_paths() -> RuntimePaths:
    return resolve_runtime_paths()
