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
            if kwargs.get("engine"):
                db["engine"] = kwargs["engine"]
            return db
        db = {
            "id": database_id,
            "name": name or database_id,
            "description": description or "",
            "status": "active",
            "engine": kwargs.get("engine", "raganything"),
            "documents": [],
            "working_dir": "",
            "output_dir": "",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self._databases[database_id] = db
        return db

    def update_database(self, database_id, name=None, description=None, status=None, engine=None):
        if database_id not in self._databases:
            raise KeyError(f"Database '{database_id}' not found")
        db = self._databases[database_id]
        if name is not None:
            db["name"] = name
        if description is not None:
            db["description"] = description
        if status is not None:
            db["status"] = status
        if engine is not None:
            db["engine"] = engine
        return db

    def list_documents(self, database_id):
        if database_id not in self._databases:
            raise KeyError(f"Database '{database_id}' not found")
        return self._databases[database_id].get("documents", [])

    def register_document(
        self,
        database_id,
        file_name,
        file_path,
        sha256,
        source=None,
        status="已导入",
        error="",
        stored_file_name=None,
        engine=None,
        chunk_count=0,
        embedding_model="",
        rerank_model="",
    ):
        from datetime import datetime, timezone
        self.register_database(database_id)
        documents = self._databases[database_id].setdefault("documents", [])
        documents[:] = [doc for doc in documents if doc.get("sha256") != sha256]
        now = datetime.now(timezone.utc).isoformat()
        documents.append(
            {
                "file_name": file_name,
                "stored_file_name": stored_file_name or Path(file_path).name,
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
                "cleanup_status": "",
                "rag_doc_ids": [],
                "engine": engine or self._databases.get(database_id, {}).get("engine", "traditional"),
                "index_status": "indexed" if status in {"已导入", "success"} else "",
                "chunk_count": int(chunk_count or 0),
                "embedding_model": embedding_model,
                "rerank_model": rerank_model,
                "imported_at": now,
                "updated_at": now,
            }
        )

    def update_document_progress(self, database_id, sha256, **progress):
        docs = self.list_documents(database_id)
        for doc in docs:
            if doc.get("sha256") == sha256:
                doc.update(progress)
                return True
        return False

    def update_document_status(self, database_id, sha256, status, error=""):
        docs = self.list_documents(database_id)
        for doc in docs:
            if doc.get("sha256") == sha256:
                doc["status"] = status
                doc["error"] = error
                return True
        return False

    def update_document_index_metadata(
        self,
        database_id,
        sha256,
        engine=None,
        index_status=None,
        chunk_count=None,
        embedding_model=None,
        rerank_model=None,
    ):
        docs = self.list_documents(database_id)
        for doc in docs:
            if doc.get("sha256") == sha256:
                if engine is not None:
                    doc["engine"] = engine
                if index_status is not None:
                    doc["index_status"] = index_status
                if chunk_count is not None:
                    doc["chunk_count"] = int(chunk_count or 0)
                if embedding_model is not None:
                    doc["embedding_model"] = embedding_model
                if rerank_model is not None:
                    doc["rerank_model"] = rerank_model
                return True
        return False

    def delete_document(self, database_id, sha256):
        docs = self.list_documents(database_id)
        before = len(docs)
        self._databases[database_id]["documents"] = [
            doc for doc in docs if doc.get("sha256") != sha256
        ]
        return len(self._databases[database_id]["documents"]) < before


class FakeService:
    def __init__(self):
        self.registry = FakeRegistry()
        self.ingested = []

    async def ingest_file(self, database_id, file_path, source=None):
        self.ingested.append((database_id, str(file_path)))
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

    def test_register_forces_traditional_engine(self, monkeypatch):
        client, _ = _make_client(monkeypatch)
        response = client.post(
            "/db/register",
            json={"id": "engine-db", "engine": "raganything"},
        )

        assert response.status_code == 200
        assert response.json()["database"]["engine"] == "traditional"

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

    def test_update_rejects_raganything_engine(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("my-db")

        response = client.put("/db/my-db", json={"engine": "raganything"})

        assert response.status_code == 400
        assert "RAG-Anything" in response.json()["detail"]


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

    def test_documents_include_engine_and_index_status(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("kb", engine="traditional")
        service.registry.register_document(
            "kb",
            "guide.md",
            "guide.md",
            "sha",
            engine="traditional",
            chunk_count=2,
            embedding_model="BAAI/bge-m3",
        )

        response = client.get("/db/kb/documents")

        assert response.status_code == 200
        doc = response.json()["documents"][0]
        assert doc["engine"] == "traditional"
        assert doc["chunk_count"] == 2
        assert doc["embedding_model"] == "BAAI/bge-m3"

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

    def test_startup_recovery_marks_unfinished_processing_as_error(self, tmp_path):
        service = FakeService()
        service.registry.register_database("doc-db")
        service.registry.register_document(
            "doc-db",
            file_name="stuck.pdf",
            file_path=str(tmp_path / "stuck.pdf"),
            sha256="sha-stuck",
            status="processing",
        )

        rag_api._recover_interrupted_processing_documents(service)

        doc = service.registry.list_documents("doc-db")[0]
        assert doc["status"] == "error"
        assert "服务重启" in doc["error"]
        assert doc["stage"] == "interrupted"


def test_startup_recovery_marks_uploaded_stage_as_retryable_error(tmp_path):
    service = FakeService()
    service.registry.register_database("kb")
    source = tmp_path / "stuck.pdf"
    source.write_bytes(b"pdf")
    service.registry.register_document(
        "kb",
        file_name="stuck.pdf",
        file_path=str(source),
        sha256="sha-stuck",
        status="processing",
    )
    service.registry.update_document_progress("kb", "sha-stuck", stage="rag_ingest")

    rag_api._recover_interrupted_processing_documents(service)

    doc = service.registry.list_documents("kb")[0]
    assert doc["status"] == "error"
    assert doc["stage"] == "interrupted"
    assert "请删除后重新上传或使用重试" in doc["error"]


class TestDeleteDocument:
    def test_delete_document_cleans_lightrag_residue(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("doc-db")
        upload_file = tmp_path / "files" / "doc-db" / "book.pdf"
        upload_file.parent.mkdir(parents=True)
        upload_file.write_bytes(b"pdf")
        service.registry.register_document(
            "doc-db",
            file_name="book.pdf",
            file_path=str(upload_file),
            sha256="sha-book",
            status="error",
            error="interrupted",
        )
        status_dir = tmp_path / "doc-db" / "rag_storage"
        status_dir.mkdir(parents=True)
        (status_dir / "kv_store_doc_status.json").write_text(
            json.dumps(
                {
                    "doc-book": {
                        "status": "processing",
                        "file_path": "book.pdf",
                        "chunks_list": ["chunk-a", "chunk-b"],
                    },
                    "doc-other": {
                        "status": "processed",
                        "file_path": "other.pdf",
                        "chunks_list": ["chunk-c"],
                    },
                }
            ),
            encoding="utf-8",
        )
        (status_dir / "kv_store_full_docs.json").write_text(
            json.dumps(
                {
                    "doc-book": {"content": "stale", "file_path": "book.pdf"},
                    "doc-other": {"content": "keep", "file_path": "other.pdf"},
                }
            ),
            encoding="utf-8",
        )
        (status_dir / "kv_store_text_chunks.json").write_text(
            json.dumps(
                {
                    "chunk-a": {"content": "stale a", "full_doc_id": "doc-book"},
                    "chunk-b": {"content": "stale b", "full_doc_id": "doc-book"},
                    "chunk-c": {"content": "keep", "full_doc_id": "doc-other"},
                }
            ),
            encoding="utf-8",
        )
        (status_dir / "vdb_chunks.json").write_text(
            json.dumps(
                {
                    "embedding_dim": 1024,
                    "data": [
                        {"__id__": "chunk-a", "full_doc_id": "doc-book", "file_path": "book.pdf"},
                        {"__id__": "chunk-c", "full_doc_id": "doc-other", "file_path": "other.pdf"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (status_dir / "graph_chunk_entity_relation.graphml").write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <graph edgedefault="undirected">
    <node id="stale"><data key="source_id">chunk-a</data></node>
    <node id="keep"><data key="source_id">chunk-c</data></node>
    <edge id="e-stale" source="stale" target="keep"><data key="source_id">chunk-b</data></edge>
  </graph>
</graphml>
""",
            encoding="utf-8",
        )
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)
        output_dir = tmp_path / "output" / "doc-db"
        stale_output = output_dir / "book_abcd1234"
        keep_output = output_dir / "other_abcd1234"
        stale_output.mkdir(parents=True)
        keep_output.mkdir(parents=True)
        (stale_output / "book.md").write_text("stale", encoding="utf-8")
        (keep_output / "other.md").write_text("keep", encoding="utf-8")
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_OUTPUT_ROOT", tmp_path / "output")

        response = client.delete("/db/doc-db/documents/sha-book")

        assert response.status_code == 200
        assert not upload_file.exists()
        assert not stale_output.exists()
        assert keep_output.exists()
        assert service.registry.list_documents("doc-db") == []
        doc_status = json.loads((status_dir / "kv_store_doc_status.json").read_text(encoding="utf-8"))
        full_docs = json.loads((status_dir / "kv_store_full_docs.json").read_text(encoding="utf-8"))
        text_chunks = json.loads((status_dir / "kv_store_text_chunks.json").read_text(encoding="utf-8"))
        vdb_chunks = json.loads((status_dir / "vdb_chunks.json").read_text(encoding="utf-8"))
        graphml = (status_dir / "graph_chunk_entity_relation.graphml").read_text(encoding="utf-8")
        assert "doc-book" not in doc_status
        assert "doc-book" not in full_docs
        assert "chunk-a" not in text_chunks
        assert "chunk-b" not in text_chunks
        assert [item["__id__"] for item in vdb_chunks["data"]] == ["chunk-c"]
        assert "chunk-a" not in graphml
        assert "chunk-b" not in graphml
        assert "chunk-c" in graphml


class TestRetryDocument:
    def test_retry_traditional_document_short_circuits_already_indexed(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("video", engine="traditional")
        source = tmp_path / "clip.mp4"
        source.write_bytes(b"video")
        service.registry.register_document(
            "video",
            file_name="clip.mp4",
            file_path=str(source),
            sha256="abc",
            status="error",
            error="previous request failed",
        )
        service.registry.update_document_index_metadata(
            "video",
            "abc",
            engine="traditional",
            index_status="indexed",
            chunk_count=3,
            embedding_model="embed",
        )

        class FakeTraditionalEngine:
            async def ingest_file(self, database_id, file_path):
                raise AssertionError("already indexed documents should not be reprocessed")

        monkeypatch.setattr(rag_api, "traditional_service", FakeTraditionalEngine())

        response = client.post(
            "/db/video/documents/abc/retry",
            json={"strategy": "markdown_segments"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        doc = service.registry.list_documents("video")[0]
        assert doc["status"] == "已导入"
        assert doc["stage"] == "done"
        assert doc["chunk_count"] == 3

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

    def test_retry_document_not_found_returns_404(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("kb")

        response = client.post(
            "/db/kb/documents/nonexistent/retry",
            json={"strategy": "markdown_segments"},
        )

        assert response.status_code == 404
        assert "文档不存在" in response.json()["detail"]

    def test_retry_document_processing_returns_409(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("kb")
        service.registry.register_document(
            "kb",
            file_name="book.pdf",
            file_path=str(tmp_path / "book.pdf"),
            sha256="abc",
            status="processing",
        )

        response = client.post(
            "/db/kb/documents/abc/retry",
            json={"strategy": "markdown_segments"},
        )

        assert response.status_code == 409
        assert "正在处理中" in response.json()["detail"]


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

    def test_background_upload_records_processing_stage(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("stage-db")
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        observed_stage = {}

        def _ingest(*args, **kwargs):
            docs = service.registry.list_documents("stage-db")
            observed_stage["stage"] = docs[0].get("stage")
            return {"status": "success"}

        service.ingest_file_sync = _ingest

        response = client.post(
            "/ingest/upload",
            data={"database": "stage-db"},
            files={"files": ("slow.pdf", io.BytesIO(b"data"), "application/pdf")},
        )
        assert response.status_code == 200

        import time
        time.sleep(1.5)

        assert observed_stage["stage"] == "rag_ingest"

    def test_traditional_background_upload_marks_document_indexed(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("trad-db", engine="traditional")
        monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

        class FakeTraditionalEngine:
            async def ingest_file(self, database_id, file_path):
                return {
                    "status": "success",
                    "database": database_id,
                    "document_sha256": "unused",
                    "file_name": Path(file_path).name,
                    "engine": "traditional",
                    "chunk_count": 3,
                    "embedding_model": "custom-embedding",
                    "rerank_model": "custom-rerank",
                }

        monkeypatch.setattr(rag_api, "traditional_service", FakeTraditionalEngine())

        response = client.post(
            "/ingest/upload",
            data={"database": "trad-db"},
            files={"files": ("guide.md", io.BytesIO("开通说明".encode("utf-8")), "text/markdown")},
        )
        assert response.status_code == 200

        import time
        time.sleep(1.5)

        doc = service.registry.list_documents("trad-db")[0]
        assert doc["status"] == "已导入"
        assert doc["stage"] == "done"
        assert doc["index_status"] == "indexed"
        assert doc["chunk_count"] == 3
        assert doc["embedding_model"] == "custom-embedding"

    def test_ingest_path_directory_uses_selected_engine(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("dir-db", engine="raganything")
        source = tmp_path / "source"
        source.mkdir()
        (source / "a.txt").write_text("hello", encoding="utf-8")

        response = client.post(
            "/ingest/path",
            json={"database": "dir-db", "path": str(source), "recursive": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["success_files"] == 1
        assert service.ingested == [("dir-db", str(source / "a.txt"))]

    def test_ingest_path_file_records_traditional_document(self, monkeypatch, tmp_path):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("path-trad-db", engine="traditional")
        source = tmp_path / "guide.md"
        source.write_text("hello", encoding="utf-8")

        class FakeTraditionalEngine:
            async def ingest_file(self, database_id, file_path):
                return {
                    "status": "success",
                    "database": database_id,
                    "document_sha256": rag_api._sha256(Path(file_path)),
                    "file_name": Path(file_path).name,
                    "engine": "traditional",
                    "chunk_count": 2,
                    "embedding_model": "embed-model",
                }

        monkeypatch.setattr(rag_api, "traditional_service", FakeTraditionalEngine())

        response = client.post(
            "/ingest/path",
            json={"database": "path-trad-db", "path": str(source), "recursive": False},
        )

        assert response.status_code == 200
        doc = service.registry.list_documents("path-trad-db")[0]
        assert doc["file_name"] == "guide.md"
        assert doc["status"] == "已导入"
        assert doc["index_status"] == "indexed"
        assert doc["chunk_count"] == 2


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

    def test_list_includes_engine_field(self, monkeypatch):
        client, service = _make_client(monkeypatch)
        service.registry.register_database("trad-kb", engine="traditional")
        service.registry.register_database("rag-kb")

        response = client.get("/db/list")
        assert response.status_code == 200
        by_id = {d["id"]: d for d in response.json()["databases"]}
        assert by_id["trad-kb"]["engine"] == "traditional"
        assert by_id["rag-kb"]["engine"] == "raganything"


def test_database_audit_endpoint_reports_orphans(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch)
    db = service.registry.register_database(
        "audit-db",
        working_dir=str(tmp_path / "audit-db" / "rag_storage"),
        output_dir=str(tmp_path / "output" / "audit-db"),
    )
    db["working_dir"] = str(tmp_path / "audit-db" / "rag_storage")
    registered_file = tmp_path / "registered.pdf"
    registered_file.write_bytes(b"registered")
    service.registry.register_document(
        "audit-db",
        file_name="registered.pdf",
        file_path=str(registered_file),
        sha256="sha-registered",
        status="已导入",
    )
    working_dir = tmp_path / "audit-db" / "rag_storage"
    working_dir.mkdir(parents=True)
    (working_dir / "kv_store_text_chunks.json").write_text(
        json.dumps({"chunk-1": {"content": "x", "file_path": "orphan.pdf"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get("/db/audit-db/audit")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["audit"]["orphan_sources"] == ["orphan.pdf"]
    assert data["audit"]["missing_registered_files"] == []
    assert data["audit"]["contaminated"] is True


def test_upload_same_filename_keeps_distinct_physical_files(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch)
    service.registry.register_database("upload-db")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path)

    first = client.post(
        "/ingest/upload",
        data={"database": "upload-db"},
        files={"files": ("same.txt", io.BytesIO(b"first"), "text/plain")},
    )
    second = client.post(
        "/ingest/upload",
        data={"database": "upload-db"},
        files={"files": ("same.txt", io.BytesIO(b"second"), "text/plain")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    docs = service.registry.list_documents("upload-db")
    paths = [Path(doc["file_path"]).name for doc in docs]
    assert len(paths) == 2
    assert len(set(paths)) == 2
    assert all(path.startswith("same") for path in paths)
