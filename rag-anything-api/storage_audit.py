import json
from pathlib import Path
from typing import Any


LIGHTRAG_SOURCE_FILES = (
    "kv_store_text_chunks.json",
    "kv_store_full_docs.json",
    "kv_store_parse_cache.json",
)


def _source_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    source = value.get("file_path") or value.get("source") or value.get("file_name")
    return Path(str(source or "")).name.strip()


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def registered_sources(registry, database_id: str) -> set[str]:
    docs = registry.list_documents(database_id)
    sources = set()
    for doc in docs:
        for key in ("file_name", "source", "stored_file_name"):
            name = Path(str(doc.get(key) or "")).name.strip()
            if name:
                sources.add(name)
    return sources


def lightrag_sources(working_dir: Path) -> set[str]:
    sources = set()
    for filename in LIGHTRAG_SOURCE_FILES:
        data = _load_json_dict(working_dir / filename)
        for value in data.values():
            name = _source_name(value)
            if name:
                sources.add(name)
    return sources


def audit_database_storage(registry, database_id: str) -> dict[str, Any]:
    database = registry.get_database(database_id)
    if database is None:
        raise KeyError(f"Database '{database_id}' not found")

    docs = registry.list_documents(database_id)
    working_dir = Path(database.get("working_dir") or "")
    registered = registered_sources(registry, database_id)
    stored_sources = lightrag_sources(working_dir) if working_dir else set()

    missing_files = []
    for doc in docs:
        path = Path(str(doc.get("file_path") or ""))
        if path and not path.exists():
            missing_files.append(Path(str(doc.get("file_name") or path.name)).name)

    orphan_sources = sorted(source for source in stored_sources if source not in registered)
    return {
        "database": database_id,
        "registered_documents": len(docs),
        "registered_sources": sorted(registered),
        "stored_sources": sorted(stored_sources),
        "orphan_sources": orphan_sources,
        "missing_registered_files": sorted(missing_files),
        "contaminated": bool(orphan_sources or missing_files),
    }
