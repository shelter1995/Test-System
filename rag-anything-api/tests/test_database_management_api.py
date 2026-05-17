"""
知识库管理 API 测试：
- POST /db/register  创建知识库
- PUT  /db/{db_id}   更新知识库
- GET  /db/{db_id}/documents  列出文档
- POST /ingest/upload  上传文件并导入
"""

import io
import json
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

import app as rag_api


# ── Fake registry / service ──────────────────────────────────────────────


class FakeRegistry:
    """可变的内存注册表，支持 register / update / list_documents。"""

    def __init__(self):
        self._databases: dict[str, dict] = {}

    def list_databases(self):
        return list(self._databases.values())

    def get_database(self, db_id: str):
        return self._databases.get(db_id)

    def register_database(self, database_id, name=None, description="", **kwargs):
        database_id = str(database_id).strip()
        if not database_id:
            raise ValueError("database_id must not be empty")
        if database_id in self._databases:
            db = self._databases[database_id]
            if name:
                db["name"] = name
            if description is not None:
                db["description"] = description
            return db
        db = {
            "id": database_id,
            "name": name or database_id,
            "description": description or "",
            "status": "active",
            "engine": "raganything",
            "documents": [],
            "working_dir": "",
            "output_dir": "",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self._databases[database_id] = db
        return db

    def update_database(self, database_id, name=None, description=None, status=None):
        if database_id not in self._databases:
            raise KeyError(f"Database '{database_id}' not found")
        db = self._databases[database_id]
        if name is not None:
            db["name"] = name
        if description is not None:
            db["description"] = description
        if status is not None:
            db["status"] = status
        return db

    def list_documents(self, database_id):
        if database_id not in self._databases:
            raise KeyError(f"Database '{database_id}' not found")
        return self._databases[database_id].get("documents", [])

    def register_document(self, database_id, file_name, file_path, sha256, source=None, status="已导入", error=""):
        self.register_database(database_id)
        documents = self._databases[database_id].setdefault("documents", [])
        documents[:] = [doc for doc in documents if doc.get("sha256") != sha256]
        documents.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "sha256": sha256,
                "source": source or file_name,
                "status": status,
                "error": error,
            }
        )

    def update_document_status(self, database_id, sha256, status, error=""):
        docs = self.list_documents(database_id)
        for doc in docs:
            if doc.get("sha256") == sha256:
                doc["status"] = status
                doc["error"] = error
                return True
        return False


class FakeService:
    def __init__(self):
        self.registry = FakeRegistry()

    async def ingest_file(self, database_id, file_path, source=None):
        return {"status": "success", "database": database_id, "file": str(file_path)}

    def ingest_file_sync(self, database_id, file_path, source=None):
        return {"status": "success", "database": database_id, "file": str(file_path)}


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_client(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(rag_api, "rag_service", service)
    monkeypatch.setattr(rag_api, "startup_error", None)
    return TestClient(rag_api.app), service


# ── POST /db/register ────────────────────────────────────────────────────


class TestRegisterDatabase:
    def test_register_new_database(self, monkeypatch):
        client, _ = _make_client(monkeypatch)
        response = client.post(
            "/db/register",
            json={"id": "test-db", "name": "Test DB", "description": "A test KB"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["database"]["id"] == "test-db"
        assert data["database"]["name"] == "Test DB"
        assert data["database"]["description"] == "A test KB"

    def test_register_minimal(self, monkeypatch):
        """只传 id，其他字段用默认值。"""
        client, _ = _make_client(monkeypatch)
        response = client.post("/db/register", json={"id": "minimal-db"})
        assert response.status_code == 200
        data = response.json()
        assert data["database"]["id"] == "minimal-db"
        assert data["database"]["name"] == "minimal-db"
        assert data["database"]["description"] == ""

    def test_register_existing_updates(self, monkeypatch):
        """对已存在的 id 再次 register 应更新而非报错。"""
        client, service = _make_client(monkeypatch)
        service.registry.register_database("dup-db", description="old")
        response = client.post(
            "/db/register",
            json={"id": "dup-db", "description": "new"},
        )
        assert response.status_code == 200
        assert response.json()["database"]["description"] == "new"

    def test_register_empty_id_returns_400(self, monkeypatch):
        client, _ = _make_client(monkeypatch)
        response = client.post("/db/register", json={"id": ""})
        assert response.status_code == 400


# ── PUT /db/{db_id} ──────────────────────────────────────────────────────


class TestUpdateDatabase:
    def test_update_name(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("my-db", name="Old Name")
        response = client.put("/db/my-db", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["database"]["name"] == "New Name"

    def test_update_description(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("my-db")
        response = client.put("/db/my-db", json={"description": "Updated desc"})
        assert response.status_code == 200
        assert response.json()["database"]["description"] == "Updated desc"

    def test_update_status(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("my-db")
        response = client.put("/db/my-db", json={"status": "archived"})
        assert response.status_code == 200
        assert response.json()["database"]["status"] == "archived"

    def test_update_multiple_fields(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("my-db")
        response = client.put(
            "/db/my-db",
            json={"name": "X", "description": "Y", "status": "paused"},
        )
        assert response.status_code == 200
        db = response.json()["database"]
        assert db["name"] == "X"
        assert db["description"] == "Y"
        assert db["status"] == "paused"

    def test_update_nonexistent_returns_404(self, monkeypatch):
        client, _ = _make_client(monkeypatch)
        response = client.put("/db/no-such-db", json={"name": "X"})
        assert response.status_code == 404


# ── GET /db/{db_id}/documents ────────────────────────────────────────────


class TestListDocuments:
    def test_list_documents_empty(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("doc-db")
        response = client.get("/db/doc-db/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["database"] == "doc-db"
        assert data["documents"] == []

    def test_list_documents_with_data(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("doc-db")
        # 直接注入文档数据
        service.registry._databases["doc-db"]["documents"] = [
            {"file_name": "a.pdf", "sha256": "aaa"},
            {"file_name": "b.png", "sha256": "bbb"},
        ]
        response = client.get("/db/doc-db/documents")
        assert response.status_code == 200
        docs = response.json()["documents"]
        assert len(docs) == 2
        names = {d["file_name"] for d in docs}
        assert names == {"a.pdf", "b.png"}

    def test_list_documents_nonexistent_returns_404(self, monkeypatch):
        client, _ = _make_client(monkeypatch)
        response = client.get("/db/no-such-db/documents")
        assert response.status_code == 404

    def test_list_documents_reconciles_failed_lightrag_status(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("doc-db")
        service.registry.register_document(
            "doc-db",
            file_name="book.pdf",
            file_path=str(tmp_path / "book.pdf"),
            sha256="sha-book",
            status="processing",
        )
        status_dir = tmp_path / "doc-db" / "rag_storage"
        status_dir.mkdir(parents=True)
        (status_dir / "kv_store_doc_status.json").write_text(
            json.dumps(
                {
                    "doc-1": {
                        "status": "failed",
                        "file_path": "book.pdf",
                        "error_msg": "LLM func: Worker execution timeout after 360s",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        response = client.get("/db/doc-db/documents")

        assert response.status_code == 200
        doc = response.json()["documents"][0]
        assert doc["status"] == "error"
        assert "Worker execution timeout" in doc["error"]

    def test_list_documents_treats_duplicate_as_imported_when_original_processed(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("doc-db")
        service.registry.register_document(
            "doc-db",
            file_name="repeat.pdf",
            file_path=str(tmp_path / "repeat.pdf"),
            sha256="sha-repeat",
            status="processing",
        )
        status_dir = tmp_path / "doc-db" / "rag_storage"
        status_dir.mkdir(parents=True)
        (status_dir / "kv_store_doc_status.json").write_text(
            json.dumps(
                {
                    "doc-original": {
                        "status": "processed",
                        "file_path": "repeat.pdf",
                        "updated_at": "2026-01-01T00:00:00+00:00",
                    },
                    "dup-latest": {
                        "status": "failed",
                        "file_path": "repeat.pdf",
                        "error_msg": "Content already exists. Original doc_id: doc-original",
                        "metadata": {"is_duplicate": True, "original_doc_id": "doc-original"},
                        "updated_at": "2026-01-02T00:00:00+00:00",
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        response = client.get("/db/doc-db/documents")

        assert response.status_code == 200
        doc = response.json()["documents"][0]
        assert doc["status"] == "已导入"
        assert doc["error"] == ""


class TestRetryDocument:
    def test_retry_document_uses_segment_strategy(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("kb")
        service.registry.register_document(
            "kb",
            file_name="book.pdf",
            file_path=str(tmp_path / "book.pdf"),
            sha256="abc",
            status="error",
            error="timeout",
        )
        calls = []

        def recover(database_id, file_path, sha256, max_chars=12000):
            calls.append((database_id, Path(file_path).name, sha256))
            service.registry.update_document_status(
                database_id, sha256, "partial_success", "1 segment failed"
            )
            return {"status": "partial_success"}

        service.recover_from_mineru_markdown = recover

        response = client.post(
            "/db/kb/documents/abc/retry",
            json={"strategy": "markdown_segments"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "partial_success"
        assert calls == [("kb", "book.pdf", "abc")]

    def test_retry_document_runs_recover_off_event_loop(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("kb")
        service.registry.register_document(
            "kb",
            file_name="book.pdf",
            file_path=str(tmp_path / "book.pdf"),
            sha256="abc",
            status="error",
            error="timeout",
        )

        def recover(database_id, file_path, sha256, max_chars=12000):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return {"status": "partial_success"}
            raise RuntimeError("called in event loop")

        service.recover_from_mineru_markdown = recover

        response = client.post(
            "/db/kb/documents/abc/retry",
            json={"strategy": "markdown_segments"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "partial_success"


# ── POST /ingest/upload ──────────────────────────────────────────────────


class TestIngestUpload:
    def test_upload_file(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("upload-db")

        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        file_content = b"hello world"
        response = client.post(
            "/ingest/upload",
            data={"database": "upload-db"},
            files={"files": ("test.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["database"] == "upload-db"
        assert data["total"] == 1
        assert "task_id" in data

        # verify file was saved
        saved = tmp_path / "files" / "upload-db" / "test.txt"
        assert saved.exists()
        assert saved.read_bytes() == file_content

        docs = service.registry.list_documents("upload-db")
        assert docs[0]["file_name"] == "test.txt"
        assert docs[0]["status"] == "processing"

    def test_upload_multiple_files(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("multi-db")
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        response = client.post(
            "/ingest/upload",
            data={"database": "multi-db"},
            files=[
                ("files", ("a.txt", io.BytesIO(b"aaa"), "text/plain")),
                ("files", ("b.txt", io.BytesIO(b"bbb"), "text/plain")),
            ],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        saved_a = tmp_path / "files" / "multi-db" / "a.txt"
        saved_b = tmp_path / "files" / "multi-db" / "b.txt"
        assert saved_a.exists()
        assert saved_b.exists()

    def test_upload_empty_database_returns_422(self, monkeypatch):
        """FastAPI Form 验证拒绝空 database 字段。"""
        client, _ = _make_client(monkeypatch)
        response = client.post(
            "/ingest/upload",
            data={"database": ""},
            files={"files": ("test.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code == 422

    def test_upload_ingest_failure_reported_via_sse(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("fail-db")
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        def _fail(*args, **kwargs):
            raise RuntimeError("ingest boom")

        service.ingest_file_sync = _fail

        response = client.post(
            "/ingest/upload",
            data={"database": "fail-db"},
            files={"files": ("bad.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        # 等待后台处理完成，SSE 应报告错误
        import time
        time.sleep(1.5)

        from progress import progress_tracker
        events, _, finished = progress_tracker.get_events_since(task_id, 0)
        assert finished
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "ingest boom" in error_events[0]["error"]

        docs = service.registry.list_documents("fail-db")
        assert docs[0]["file_name"] == "bad.txt"
        assert docs[0]["status"] == "error"
        assert "ingest boom" in docs[0]["error"]


# ── /db/list includes description and documents_count ────────────────────


class TestDbListUpdatedFields:
    def test_list_includes_description_and_documents_count(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("alpha", description="Alpha KB")
        service.registry._databases["alpha"]["documents"] = [
            {"file_name": "x.pdf", "sha256": "x"},
            {"file_name": "y.pdf", "sha256": "y"},
        ]
        service.registry.register_database("beta")

        response = client.get("/db/list")
        assert response.status_code == 200
        data = response.json()
        by_id = {d["id"]: d for d in data["databases"]}
        assert by_id["alpha"]["description"] == "Alpha KB"
        assert by_id["alpha"]["documents_count"] == 2
        assert by_id["beta"]["description"] == ""
        assert by_id["beta"]["documents_count"] == 0
