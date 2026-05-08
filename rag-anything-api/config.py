"""
RAG-Anything API 配置
"""

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _safe_int(value: str, default: int) -> int:
    """安全的整数转换，失败时返回默认值"""
    try:
        return int(value)
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


# 加载 .env
ENV_PATH = Path(__file__).resolve().parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


# 路径配置
BASE_DIR = Path(__file__).resolve().parent
STORAGE_ROOT = BASE_DIR / "storage"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

LEGACY_LIGHTRAG_DIR = STORAGE_ROOT / "lightrag"
LEGACY_LIGHTRAG_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR = str(LEGACY_LIGHTRAG_DIR)  # 向后兼容：旧字段

RAGANYTHING_STORAGE_ROOT = STORAGE_ROOT / "raganything"
RAGANYTHING_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

RAGANYTHING_OUTPUT_ROOT = BASE_DIR / "output"
RAGANYTHING_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

DATABASE_REGISTRY_FILE = STORAGE_ROOT / "databases.json"


# 服务配置
RAG_SERVICE_HOST = os.getenv("RAG_SERVICE_HOST", "0.0.0.0")
RAG_SERVICE_PORT = _safe_int(os.getenv("RAG_SERVICE_PORT", "8003"), 8003)


# MiniMax LLM
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL_M27 = os.getenv("MINIMAX_MODEL_M27", "MiniMax-M2.7")
MINIMAX_MODEL_M25 = os.getenv("MINIMAX_MODEL_M25", "MiniMax-M2.5")


# 硅基流动 Embedding
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = _safe_int(os.getenv("EMBEDDING_DIM", "1024"), 1024)
EMBEDDING_MAX_TOKENS = _safe_int(os.getenv("EMBEDDING_MAX_TOKENS", "5000"), 5000)


# 超时与批次
LLM_TIMEOUT_M27 = _safe_int(os.getenv("LLM_TIMEOUT_M27", "120"), 120)
LLM_TIMEOUT_M25 = _safe_int(os.getenv("LLM_TIMEOUT_M25", "90"), 90)
EMBEDDING_TIMEOUT = _safe_int(os.getenv("EMBEDDING_TIMEOUT", "30"), 30)
EMBEDDING_BATCH_SIZE = _safe_int(os.getenv("EMBEDDING_BATCH_SIZE", "20"), 20)


# RAG-Anything 引擎配置
RAGANYTHING_SOURCE_DIR = os.getenv("RAGANYTHING_SOURCE_DIR", r"D:\GitHub_WorkSpace\RAG-Anything")
PARSER = os.getenv("PARSER", "mineru")
PARSE_METHOD = os.getenv("PARSE_METHOD", "auto")
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "")

CHUNK_SIZE = _safe_int(os.getenv("CHUNK_SIZE", "1200"), 1200)
CHUNK_OVERLAP_SIZE = _safe_int(os.getenv("CHUNK_OVERLAP_SIZE", "100"), 100)

ENABLE_IMAGE_PROCESSING = _safe_bool(os.getenv("ENABLE_IMAGE_PROCESSING"), True)
ENABLE_TABLE_PROCESSING = _safe_bool(os.getenv("ENABLE_TABLE_PROCESSING"), True)
ENABLE_EQUATION_PROCESSING = _safe_bool(os.getenv("ENABLE_EQUATION_PROCESSING"), True)
DEFAULT_QUERY_MODE = os.getenv("DEFAULT_QUERY_MODE", "naive").strip().lower() or "naive"


# 初始数据库 ID（仅用于第一次无 registry 文件时兼容）
DEFAULT_DATABASE_IDS = [
    "商务彩铃",
]


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
