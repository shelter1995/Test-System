import asyncio
from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    def __init__(self):
        self.queries = []
        self.files = []

    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        self.queries.append((question, mode))
        return "这是商务彩铃的资费回答"

    async def process_document_complete(
        self,
        file_path,
        output_dir,
        parse_method,
        display_stats,
        backend,
    ):
        self.files.append((file_path, output_dir, parse_method, backend))


def test_query_wraps_result(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: FakeRAG(),
    )

    result = asyncio.run(service.query("商务彩铃", "资费是多少", mode="hybrid"))
    assert result["database"] == "商务彩铃"
    assert result["results"][0]["metadata"]["source"] == "raganything"
    assert "资费回答" in result["results"][0]["text"]


def test_ingest_registers_document(tmp_path: Path):
    source_file = tmp_path / "介绍.txt"
    source_file.write_text("商务彩铃介绍", encoding="utf-8")
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: FakeRAG(),
    )

    asyncio.run(service.ingest_file("商务彩铃", source_file))
    database = registry.get_database("商务彩铃")
    assert database is not None
    assert database["documents"][0]["file_name"] == "介绍.txt"


def test_ingest_text_routes_through_raganything_document_flow(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    fake_rag = FakeRAG()
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: fake_rag,
    )

    result = asyncio.run(
        service.ingest_text(
            "商务彩铃",
            "商务彩铃产品资费与办理流程说明",
            source="migration:sample.json:1",
        )
    )

    assert result["status"] == "success"
    assert result["database"] == "商务彩铃"
    assert fake_rag.files
    generated_file = Path(fake_rag.files[0][0])
    assert generated_file.exists()
    assert "来源: migration:sample.json:1" in generated_file.read_text(encoding="utf-8")

    database = registry.get_database("商务彩铃")
    assert database is not None
    assert database["documents"][0]["source"] == "migration:sample.json:1"


def test_recover_file_from_markdown_segments_updates_partial_status(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "storage",
        output_root=tmp_path / "output",
        registry=registry,
    )
    registry.register_database("kb")
    source = tmp_path / "book.pdf"
    source.write_bytes(b"pdf")
    registry.register_document("kb", "book.pdf", str(source), "abc", status="processing")
    mineru_dir = tmp_path / "output" / "kb" / "book_12345678"
    mineru_dir.mkdir(parents=True)
    (mineru_dir / "book.md").write_text("# A\nhello\n# B\nworld", encoding="utf-8")

    calls = []

    def fake_ingest(database_id, file_path, source=None):
        calls.append(Path(file_path).name)
        if Path(file_path).name.endswith("002.md"):
            raise RuntimeError("segment timeout")
        return {"status": "success"}

    service.ingest_file_sync = fake_ingest

    result = service.recover_from_mineru_markdown("kb", source, "abc", max_chars=10)

    assert result["status"] == "partial_success"
    assert calls == ["book_part_001.md", "book_part_002.md"]
    doc = registry.list_documents("kb")[0]
    assert doc["status"] == "partial_success"
    assert doc["segments_total"] == 2
    assert doc["segments_done"] == 1
    assert doc["segments_failed"] == 1


def test_recover_file_from_nested_markdown_path(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "storage",
        output_root=tmp_path / "output",
        registry=registry,
    )
    registry.register_database("kb")
    source = tmp_path / "book.pdf"
    source.write_bytes(b"pdf")
    registry.register_document("kb", "book.pdf", str(source), "abc", status="processing")
    mineru_dir = tmp_path / "output" / "kb" / "book_12345678" / "book" / "auto"
    mineru_dir.mkdir(parents=True)
    (mineru_dir / "book.md").write_text("# A\nhello", encoding="utf-8")

    calls = []

    def fake_ingest(database_id, file_path, source=None):
        calls.append(Path(file_path).name)
        return {"status": "success"}

    service.ingest_file_sync = fake_ingest

    result = service.recover_from_mineru_markdown("kb", source, "abc", max_chars=10)

    assert result["status"] == "已导入"
    assert calls == ["book_part_001.md"]


def test_recover_file_does_not_leave_segment_docs_in_registry(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "storage",
        output_root=tmp_path / "output",
        registry=registry,
    )
    registry.register_database("kb")
    source = tmp_path / "book.pdf"
    source.write_bytes(b"pdf")
    registry.register_document("kb", "book.pdf", str(source), "abc", status="processing")
    mineru_dir = tmp_path / "output" / "kb" / "book_12345678"
    mineru_dir.mkdir(parents=True)
    (mineru_dir / "book.md").write_text("# A\nhello", encoding="utf-8")

    def fake_ingest(database_id, file_path, source=None):
        segment_path = Path(file_path)
        import hashlib
        digest = hashlib.sha256(segment_path.read_bytes()).hexdigest()
        registry.register_document(
            database_id,
            file_name=segment_path.name,
            file_path=str(segment_path),
            sha256=digest,
            status="已导入",
        )
        return {"status": "success"}

    service.ingest_file_sync = fake_ingest
    service.recover_from_mineru_markdown("kb", source, "abc", max_chars=10)

    docs = registry.list_documents("kb")
    names = [doc["file_name"] for doc in docs]
    assert "book.pdf" in names
    assert "book_part_001.md" not in names


def test_recover_file_skips_newer_part_output_dirs(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(
        storage_root=tmp_path / "storage",
        output_root=tmp_path / "output",
        registry=registry,
    )
    registry.register_database("kb")
    source = tmp_path / "book.pdf"
    source.write_bytes(b"pdf")
    registry.register_document("kb", "book.pdf", str(source), "abc", status="processing")

    origin_dir = tmp_path / "output" / "kb" / "book_12345678"
    (origin_dir / "book" / "auto").mkdir(parents=True)
    (origin_dir / "book" / "auto" / "book.md").write_text("# A\nhello", encoding="utf-8")

    newer_part_dir = tmp_path / "output" / "kb" / "book_part_004_deadbeef"
    newer_part_dir.mkdir(parents=True)
    newer_part_dir.touch()
    (newer_part_dir / "note.txt").write_text("not mineru markdown", encoding="utf-8")

    calls = []

    def fake_ingest(database_id, file_path, source=None):
        calls.append(Path(file_path).name)
        return {"status": "success"}

    service.ingest_file_sync = fake_ingest
    result = service.recover_from_mineru_markdown("kb", source, "abc", max_chars=10)

    assert result["status"] == "已导入"
    assert calls == ["book_part_001.md"]
