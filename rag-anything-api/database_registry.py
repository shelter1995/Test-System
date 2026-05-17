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
                        "description": "",
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
            item.setdefault("description", "")
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
        description: str | None = None,
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
                if description is not None:
                    item["description"] = description
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
            "description": description or "",
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

    def update_database(
        self,
        database_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """更新已有知识库的 name、description、status 字段。

        Raises:
            KeyError: 当 database_id 不存在时。
        """
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")

        data = self._load()
        for item in data["databases"]:
            if str(item.get("id", "")).strip() == database_id:
                if name is not None:
                    item["name"] = name
                if description is not None:
                    item["description"] = description
                if status is not None:
                    item["status"] = status
                item["updated_at"] = self._now()
                self._save(data)
                return item

        raise KeyError(f"Database '{database_id}' not found")

    def list_documents(self, database_id: str) -> list[dict[str, Any]]:
        """返回指定知识库的文档列表。

        Raises:
            KeyError: 当 database_id 不存在时。
        """
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")

        db = self.get_database(database_id)
        if db is None:
            raise KeyError(f"Database '{database_id}' not found")
        return db.get("documents", [])

    def register_document(
        self,
        database_id: str,
        file_name: str,
        file_path: str,
        sha256: str,
        source: str | None = None,
        status: str = "已导入",
        error: str = "",
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
        now = self._now()
        documents.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "sha256": sha256,
                "source": source or file_name,
                "status": status,
                "error": error,
                "stage": "",
                "segments_total": 0,
                "segments_done": 0,
                "segments_failed": 0,
                "partial_errors": [],
                "imported_at": now,
                "updated_at": now,
            }
        )
        database["updated_at"] = self._now()
        self._save(data)

    def update_document_status(
        self,
        database_id: str,
        sha256: str,
        status: str,
        error: str = "",
    ) -> bool:
        database_id = str(database_id).strip()
        sha256 = str(sha256).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")
        if not sha256:
            raise ValueError("sha256 must not be empty")

        data = self._load()
        for item in data["databases"]:
            if str(item.get("id", "")).strip() != database_id:
                continue
            for doc in item.get("documents", []):
                if doc.get("sha256") == sha256:
                    doc["status"] = status
                    doc["error"] = error
                    doc["updated_at"] = self._now()
                    item["updated_at"] = self._now()
                    self._save(data)
                    return True
            return False

        raise KeyError(f"Database '{database_id}' not found")

    def update_document_progress(
        self,
        database_id: str,
        sha256: str,
        **progress: Any,
    ) -> bool:
        database_id = str(database_id).strip()
        sha256 = str(sha256).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")
        if not sha256:
            raise ValueError("sha256 must not be empty")

        allowed = {
            "stage",
            "segments_total",
            "segments_done",
            "segments_failed",
            "partial_errors",
        }

        data = self._load()
        for item in data["databases"]:
            if str(item.get("id", "")).strip() != database_id:
                continue
            for doc in item.get("documents", []):
                if doc.get("sha256") == sha256:
                    for key, value in progress.items():
                        if key in allowed:
                            doc[key] = value
                    doc["updated_at"] = self._now()
                    item["updated_at"] = self._now()
                    self._save(data)
                    return True
            return False

        raise KeyError(f"Database '{database_id}' not found")

    def delete_database(self, database_id: str) -> bool:
        """删除知识库，返回是否成功删除。

        Raises:
            KeyError: 当 database_id 不存在时。
        """
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")

        data = self._load()
        for i, item in enumerate(data["databases"]):
            if str(item.get("id", "")).strip() == database_id:
                data["databases"].pop(i)
                self._save(data)
                return True

        raise KeyError(f"Database '{database_id}' not found")

    def delete_document(self, database_id: str, sha256: str) -> bool:
        """删除知识库中的文档，返回是否成功删除。

        Raises:
            KeyError: 当 database_id 不存在时。
        """
        database_id = str(database_id).strip()
        sha256 = str(sha256).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")
        if not sha256:
            raise ValueError("sha256 must not be empty")

        data = self._load()
        db = None
        for item in data["databases"]:
            if str(item.get("id", "")).strip() == database_id:
                db = item
                break

        if db is None:
            raise KeyError(f"Database '{database_id}' not found")

        documents = db.get("documents", [])
        before = len(documents)
        db["documents"] = [d for d in documents if d.get("sha256", "") != sha256]
        db["updated_at"] = self._now()
        self._save(data)
        return len(db["documents"]) < before
