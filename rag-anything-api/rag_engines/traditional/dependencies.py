from __future__ import annotations

import os
import shutil
from importlib.util import find_spec


DependencyInfo = dict[str, str | bool]
DependencyMap = dict[str, DependencyInfo]


def _normalize_path(value: str | None) -> str:
    return str(value or "").strip()


def _module_available(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def _resolve_libreoffice_path() -> str:
    env_path = _normalize_path(os.getenv("LIBREOFFICE_PATH"))
    if env_path:
        return env_path
    return _normalize_path(shutil.which("soffice") or shutil.which("libreoffice"))


def _resolve_mineru_path() -> str:
    env_path = _normalize_path(os.getenv("MINERU_CLI_PATH"))
    if env_path:
        return env_path
    python_path = _normalize_path(os.getenv("MINERU_PYTHON"))
    if python_path and _module_available("mineru.cli.client"):
        return python_path
    return _normalize_path(shutil.which("mineru"))


def _detect_whisper_cli_path() -> str:
    cli_path = _normalize_path(shutil.which("whisper"))
    if cli_path:
        return cli_path
    spec = find_spec("whisper")
    if spec and spec.origin:
        return _normalize_path(spec.origin)
    return ""


def _build_dependency_entry(path: str) -> DependencyInfo:
    return {"available": bool(path), "path": path}


def detect_traditional_parser_dependencies() -> DependencyMap:
    ffmpeg_path = _normalize_path(shutil.which("ffmpeg"))
    libreoffice_path = _resolve_libreoffice_path()
    mineru_path = _resolve_mineru_path()
    whisper_path = _detect_whisper_cli_path()

    return {
        "ffmpeg": _build_dependency_entry(ffmpeg_path),
        "libreoffice": _build_dependency_entry(libreoffice_path),
        "mineru": _build_dependency_entry(mineru_path),
        "whisper": _build_dependency_entry(whisper_path),
    }

