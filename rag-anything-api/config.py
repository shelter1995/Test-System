"""
传统 RAG 知识库服务配置。
历史 RAG-Anything 相关配置仅用于旧数据兼容读取。
"""

import json
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from importlib.util import find_spec

from dotenv import load_dotenv
from rag_engines.traditional.dependencies import detect_traditional_parser_dependencies


_RUNTIME_PATHS_MODULE = "_test_system_rag_runtime_paths"
if _RUNTIME_PATHS_MODULE not in sys.modules:
    runtime_paths_spec = importlib.util.spec_from_file_location(
        _RUNTIME_PATHS_MODULE,
        Path(__file__).resolve().with_name("runtime_paths.py"),
    )
    runtime_paths_module = importlib.util.module_from_spec(runtime_paths_spec)
    sys.modules[_RUNTIME_PATHS_MODULE] = runtime_paths_module
    runtime_paths_spec.loader.exec_module(runtime_paths_module)
else:
    runtime_paths_module = sys.modules[_RUNTIME_PATHS_MODULE]
absolute_env_path = runtime_paths_module.absolute_env_path


def _normalize_base_url(base_url: str, suffix: str) -> str:
    text = str(base_url or "").rstrip("/")
    if text.endswith(suffix):
        return text
    return text + suffix


def _safe_int(value: str, default: int) -> int:
    """安全的整数转换，失败时返回默认值"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: str, default: float) -> float:
    """安全的浮点数转换，失败时返回默认值"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_bool(value: str, default: bool) -> bool:
    """安全的布尔转换，失败时返回默认值"""
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _module_available(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


def _discover_winget_ffmpeg() -> str:
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if not local_app_data:
        return ""
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages.exists():
        return ""
    matches = sorted(packages.glob("Gyan.FFmpeg_*/ffmpeg-*/bin/ffmpeg.exe"), reverse=True)
    if not matches:
        return ""
    exe = matches[0]
    os.environ["PATH"] = f"{exe.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    return str(exe)


def _prepend_path(path: Path) -> str:
    text = str(path)
    entries = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if text not in entries:
        os.environ["PATH"] = os.pathsep.join([text, *entries])
    return text


def _ensure_python_scripts_on_path(executable: str | None = None) -> str:
    exe_path = Path(executable or sys.executable)
    scripts_dir = exe_path.parent
    if not scripts_dir.exists():
        return ""
    return _prepend_path(scripts_dir)


# 路径配置必须先于 dotenv，以便安装版从外置数据目录读取配置。
BASE_DIR = Path(__file__).resolve().parent
data_dir_value = os.getenv("TEST_SYSTEM_DATA_DIR", "").strip()
data_dir = Path(data_dir_value) if data_dir_value else None
if data_dir is not None and data_dir.is_absolute():
    ENV_PATH = (data_dir / "config" / "rag.env").resolve()
else:
    ENV_PATH = (BASE_DIR / ".env").resolve()
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=False)

PYTHON_SCRIPTS_DIR = _ensure_python_scripts_on_path()

# 可变数据目录：源码模式沿用原路径，安装版通过绝对环境变量外置。
STORAGE_ROOT = absolute_env_path("TEST_SYSTEM_RAG_STORAGE_DIR", BASE_DIR / "storage")
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

LEGACY_LIGHTRAG_DIR = STORAGE_ROOT / "lightrag"
LEGACY_LIGHTRAG_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR = str(LEGACY_LIGHTRAG_DIR)  # 向后兼容：旧字段

RAGANYTHING_STORAGE_ROOT = STORAGE_ROOT / "raganything"
RAGANYTHING_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

RAGANYTHING_OUTPUT_ROOT = absolute_env_path("TEST_SYSTEM_RAG_OUTPUT_DIR", BASE_DIR / "output")
RAGANYTHING_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

DATABASE_REGISTRY_FILE = STORAGE_ROOT / "databases.json"


# 服务配置
RAG_SERVICE_HOST = os.getenv("RAG_SERVICE_HOST", "0.0.0.0")
RAG_SERVICE_PORT = _safe_int(os.getenv("RAG_SERVICE_PORT", "8003"), 8003)


# 默认 LLM 兼容配置。用户可见推理模型以 model_settings.py 的运行时配置为准。
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
# 以下两个变量仅保留给历史 RAG-Anything 兼容层读取，不再作为用户可见回退策略。
MINIMAX_MODEL_M27 = os.getenv("MINIMAX_MODEL_M27", "MiniMax-M2.7")
MINIMAX_MODEL_M25 = os.getenv("MINIMAX_MODEL_M25", "MiniMax-M2.5")


# 默认 Embedding 兼容配置。实际嵌入模型可在前端模型设置中热更新。
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = _safe_int(os.getenv("EMBEDDING_DIM", "1024"), 1024)
EMBEDDING_MAX_TOKENS = _safe_int(os.getenv("EMBEDDING_MAX_TOKENS", "5000"), 5000)


# 超时与批次
LLM_TIMEOUT_M27 = _safe_int(os.getenv("LLM_TIMEOUT_M27", "120"), 120)
LLM_TIMEOUT_M25 = _safe_int(os.getenv("LLM_TIMEOUT_M25", "90"), 90)
EMBEDDING_TIMEOUT = _safe_int(os.getenv("EMBEDDING_TIMEOUT", "30"), 30)
EMBEDDING_BATCH_SIZE = _safe_int(os.getenv("EMBEDDING_BATCH_SIZE", "10"), 10)
EMBEDDING_BATCH_INTERVAL = _safe_float(os.getenv("EMBEDDING_BATCH_INTERVAL", "1.0"), 1.0)
EMBEDDING_RETRY_ATTEMPTS = _safe_int(os.getenv("EMBEDDING_RETRY_ATTEMPTS", "3"), 3)
EMBEDDING_RETRY_BASE_DELAY = _safe_float(os.getenv("EMBEDDING_RETRY_BASE_DELAY", "30"), 30.0)


# 历史 RAG-Anything 兼容配置（通过 pip install raganything 安装，无需本地 clone）
PARSER = os.getenv("PARSER", "mineru")
PARSE_METHOD = os.getenv("PARSE_METHOD", "auto")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "")

CHUNK_SIZE = _safe_int(os.getenv("CHUNK_SIZE", "1200"), 1200)
CHUNK_OVERLAP_SIZE = _safe_int(os.getenv("CHUNK_OVERLAP_SIZE", "100"), 100)

ENABLE_IMAGE_PROCESSING = _safe_bool(os.getenv("ENABLE_IMAGE_PROCESSING"), True)
ENABLE_TABLE_PROCESSING = _safe_bool(os.getenv("ENABLE_TABLE_PROCESSING"), True)
ENABLE_EQUATION_PROCESSING = _safe_bool(os.getenv("ENABLE_EQUATION_PROCESSING"), True)
ENABLE_VIDEO_PROCESSING = _safe_bool(os.getenv("ENABLE_VIDEO_PROCESSING"), False)
ENABLE_AUDIO_PROCESSING = _safe_bool(os.getenv("ENABLE_AUDIO_PROCESSING"), False)
DEFAULT_QUERY_MODE = os.getenv("DEFAULT_QUERY_MODE", "hybrid").strip().lower() or "hybrid"

FFMPEG_PATH = shutil.which("ffmpeg") or _discover_winget_ffmpeg()
WHISPER_AVAILABLE = find_spec("whisper") is not None
MINERU_PATH = shutil.which("mineru")
LIBREOFFICE_PATH = os.getenv("LIBREOFFICE_PATH", "").strip()
MINERU_CLI_PATH = os.getenv("MINERU_CLI_PATH", "").strip()
MINERU_PYTHON = os.getenv("MINERU_PYTHON", "").strip()
TRADITIONAL_PARSER_DEPENDENCIES = detect_traditional_parser_dependencies()
if not TRADITIONAL_PARSER_DEPENDENCIES["ffmpeg"]["path"] and FFMPEG_PATH:
    TRADITIONAL_PARSER_DEPENDENCIES["ffmpeg"] = {"available": True, "path": FFMPEG_PATH}
if LIBREOFFICE_PATH:
    TRADITIONAL_PARSER_DEPENDENCIES["libreoffice"] = {"available": True, "path": LIBREOFFICE_PATH}
if MINERU_CLI_PATH:
    TRADITIONAL_PARSER_DEPENDENCIES["mineru"] = {"available": True, "path": MINERU_CLI_PATH}
if not LIBREOFFICE_PATH:
    LIBREOFFICE_PATH = str(TRADITIONAL_PARSER_DEPENDENCIES["libreoffice"]["path"])
if not MINERU_CLI_PATH:
    MINERU_CLI_PATH = str(TRADITIONAL_PARSER_DEPENDENCIES["mineru"]["path"])
MINERU_PATH = str(TRADITIONAL_PARSER_DEPENDENCIES["mineru"]["path"])
if MINERU_CLI_PATH and MINERU_CLI_PATH != MINERU_PYTHON:
    MINERU_COMMAND = [MINERU_CLI_PATH]
elif MINERU_PYTHON and _module_available("mineru.cli.client"):
    MINERU_COMMAND = [MINERU_PYTHON, "-m", "mineru.cli.client"]
else:
    MINERU_COMMAND = []
WHISPER_AVAILABLE = bool(TRADITIONAL_PARSER_DEPENDENCIES["whisper"]["available"])

# VLM 图片理解（MiniMax Coding Plan 专用接口）
# POST /v1/coding_plan/vlm  {prompt, image_url} → {content}
# 与普通 /v1/chat/completions 不同，这是 Coding Plan 套餐的图片理解 API
ENABLE_VLM = _safe_bool(os.getenv("ENABLE_VLM"), False)
VLM_API_KEY = os.getenv("VLM_API_KEY") or os.getenv("MINIMAX_API_KEY") or ""
VLM_BASE_URL = os.getenv("VLM_BASE_URL", "https://api.minimaxi.com").rstrip("/")
VLM_MODEL = os.getenv("VLM_MODEL", "")  # coding_plan 接口不需要指定模型

# Rerank 重排序兼容配置。实际重排模型可在前端模型设置中热更新。
ENABLE_RERANK = _safe_bool(os.getenv("ENABLE_RERANK"), False)
RERANK_API_KEY = os.getenv("RERANK_API_KEY") or os.getenv("SILICONFLOW_API_KEY") or ""
RERANK_BASE_URL = _normalize_base_url(os.getenv("RERANK_BASE_URL", "https://api.siliconflow.cn"), "/v1")
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

# 多库并发查询超时（秒）
QUERY_ALL_TIMEOUT = _safe_int(os.getenv("QUERY_ALL_TIMEOUT", "60"), 60)
RAG_QUERY_TIMEOUT = _safe_int(os.getenv("RAG_QUERY_TIMEOUT", "8"), 8)

# 轻量上下文检索
CONTEXT_QUERY_MODE = os.getenv("CONTEXT_QUERY_MODE", "naive").strip().lower() or "naive"
CONTEXT_MAX_CHARS = _safe_int(os.getenv("CONTEXT_MAX_CHARS", "3000"), 3000)
CONTEXT_LOCAL_FIRST = _safe_bool(os.getenv("CONTEXT_LOCAL_FIRST"), True)
KB_QUERY_REWRITE_ENABLED = _safe_bool(os.getenv("KB_QUERY_REWRITE_ENABLED"), True)
KB_RETRIEVAL_CANDIDATES = _safe_int(os.getenv("KB_RETRIEVAL_CANDIDATES", "20"), 20)
KB_FINAL_CONTEXTS = _safe_int(os.getenv("KB_FINAL_CONTEXTS", "8"), 8)
KB_MIN_SCORE = _safe_float(os.getenv("KB_MIN_SCORE", "0.25"), 0.25)
KB_MAX_REWRITE_QUERIES = _safe_int(os.getenv("KB_MAX_REWRITE_QUERIES", "3"), 3)

# RAG 实例缓存上限
MAX_RAG_INSTANCES = _safe_int(os.getenv("MAX_RAG_INSTANCES", "3"), 3)


# 传统 RAG 引擎配置
DEFAULT_RAG_ENGINE = os.getenv("DEFAULT_RAG_ENGINE", "traditional").strip().lower() or "traditional"
TRADITIONAL_RAG_STORAGE_ROOT = STORAGE_ROOT / "traditional_rag"
TRADITIONAL_RAG_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
TRADITIONAL_SUPPORTED_EXTENSIONS = {
    item.strip().lower()
    for item in os.getenv(
        "TRADITIONAL_SUPPORTED_EXTENSIONS",
        ".txt,.md,.csv,.pdf,.docx,.xlsx,.pptx,.doc,.xls,.ppt,"
        ".png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,"
        ".mp3,.wav,.m4a,.aac,.flac,.ogg,.wma,"
        ".mp4,.mov,.mkv,.avi,.wmv,.webm,.m4v",
    ).split(",")
    if item.strip()
}
TRADITIONAL_CHUNK_SIZE = _safe_int(os.getenv("TRADITIONAL_CHUNK_SIZE", "1200"), 1200)
TRADITIONAL_CHUNK_OVERLAP = _safe_int(os.getenv("TRADITIONAL_CHUNK_OVERLAP", "120"), 120)


# 新安装环境从空知识库列表开始。历史数据仅通过磁盘发现逻辑恢复。
DEFAULT_DATABASE_IDS: list[str] = []


def _read_registry() -> dict[str, Any]:
    if not DATABASE_REGISTRY_FILE.exists():
        return {"databases": []}
    try:
        data = json.loads(DATABASE_REGISTRY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"databases": []}
    if isinstance(data, list):
        return {
            "databases": [
                {"id": str(item), "name": str(item), "status": "active", "engine": "raganything", "documents": []}
                for item in data
                if str(item).strip()
            ]
        }
    if not isinstance(data, dict):
        return {"databases": []}
    data.setdefault("databases", [])
    return data


def get_database_ids() -> list[str]:
    """读取当前知识库 ID 列表。"""
    data = _read_registry()
    if data["databases"]:
        ids = []
        for item in data["databases"]:
            db_id = str(item.get("id", "")).strip()
            if db_id:
                ids.append(db_id)
        return ids

    if DATABASE_REGISTRY_FILE.exists():
        return []
    return list(DEFAULT_DATABASE_IDS)


def save_database_ids(database_ids: list[str]) -> None:
    """按最小结构保存知识库列表。"""
    databases = []
    seen = set()
    for db_id in database_ids:
        db_id = str(db_id).strip()
        if not db_id or db_id in seen:
            continue
        seen.add(db_id)
        databases.append(
            {
                "id": db_id,
                "name": db_id,
                "status": "active",
                "engine": "raganything",
                "documents": [],
            }
        )
    DATABASE_REGISTRY_FILE.write_text(
        json.dumps({"databases": databases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_database_id(db_id: str) -> None:
    """兼容旧调用：登记知识库 ID。"""
    db_id = str(db_id).strip()
    if not db_id:
        return

    data = _read_registry()
    for item in data["databases"]:
        if str(item.get("id", "")).strip() == db_id:
            return
    data["databases"].append(
        {
            "id": db_id,
            "name": db_id,
            "status": "active",
            "engine": "raganything",
            "documents": [],
        }
    )
    DATABASE_REGISTRY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
