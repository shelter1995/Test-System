"""
数据库注册表管理
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DatabaseRegistry:
    def __init__(self, registry_file: str | Path):
        self.registry_file = Path(registry_file)
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _normalize_databases(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return {
                "databases": [
                    {
                        "id": str(item),
                        "name": str(item),
                        "status": "active",
                        "engine": "raganything",
                        "created_at": self._now(),
                        "updated_at": self._now(),
                        "documents": [],
                    }
                    for item in data
                    if str(item).strip()
                ]
            }
        if not isinstance(data, dict):
            return {"databases": []}
        data.setdefault("databases", [])
        for item in data["databases"]:
            item.setdefault("name", item.get("id", ""))
            item.setdefault("status", "active")
            item.setdefault("engine", "raganything")
            item.setdefault("documents", [])
            item.setdefault("created_at", self._now())
            item.setdefault("updated_at", self._now())
        return data

    def _load(self) -> dict[str, Any]:
        if not self.registry_file.exists():
            return {"databases": []}
        try:
            raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"databases": []}
        return self._normalize_databases(raw)

    def _save(self, data: dict[str, Any]) -> None:
        self.registry_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_databases(self) -> list[dict[str, Any]]:
        return self._load()["databases"]

    def get_database(self, database_id: str) -> dict[str, Any] | None:
        database_id = str(database_id).strip()
        if not database_id:
            return None
        for item in self.list_databases():
            if str(item.get("id", "")).strip() == database_id:
                return item
        return None

    def register_database(
        self,
        database_id: str,
        name: str | None = None,
        working_dir: str | None = None,
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")

        data = self._load()
        for item in data["databases"]:
            if str(item.get("id", "")).strip() == database_id:
                item["name"] = name or item.get("name") or database_id
                if working_dir:
                    item["working_dir"] = working_dir
                if output_dir:
                    item["output_dir"] = output_dir
                item["updated_at"] = self._now()
                self._save(data)
                return item

        now = self._now()
        item = {
            "id": database_id,
            "name": name or database_id,
            "status": "active",
            "engine": "raganything",
            "created_at": now,
            "updated_at": now,
            "working_dir": working_dir or "",
            "output_dir": output_dir or "",
            "documents": [],
        }
        data["databases"].append(item)
        self._save(data)
        return item

    def register_document(
        self,
        database_id: str,
        file_name: str,
        file_path: str,
        sha256: str,
        source: str | None = None,
    ) -> None:
        data = self._load()

        database = None
        for item in data["databases"]:
            if str(item.get("id", "")).strip() == str(database_id).strip():
                database = item
                break

        if database is None:
            database = self.register_database(database_id)
            data = self._load()
            for item in data["databases"]:
                if str(item.get("id", "")).strip() == str(database_id).strip():
                    database = item
                    break

        if database is None:
            return

        documents = database.setdefault("documents", [])
        documents[:] = [doc for doc in documents if doc.get("sha256") != sha256]
        documents.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "sha256": sha256,
                "source": source or file_name,
                "status": "imported",
                "imported_at": self._now(),
            }
        )
        database["updated_at"] = self._now()
        self._save(data)
