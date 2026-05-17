from pathlib import Path

from database_registry import DatabaseRegistry


def test_registry_starts_empty(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    assert registry.list_databases() == []


def test_register_database_and_document(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    registry.register_document(
        "商务彩铃",
        file_name="介绍.png",
        file_path="D:/data/介绍.png",
        sha256="abc123",
    )

    databases = registry.list_databases()
    assert len(databases) == 1
    assert databases[0]["id"] == "商务彩铃"
    assert databases[0]["engine"] == "raganything"
    assert databases[0]["documents"][0]["file_name"] == "介绍.png"


def test_register_database_deduplicates(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    registry.register_database("商务彩铃")
    assert len(registry.list_databases()) == 1


def test_register_document_accepts_processing_status_and_updates_status(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")

    registry.register_document(
        "商务彩铃",
        file_name="介绍.pdf",
        file_path="D:/data/介绍.pdf",
        sha256="abc123",
        status="processing",
    )

    doc = registry.list_documents("商务彩铃")[0]
    assert doc["file_name"] == "介绍.pdf"
    assert doc["status"] == "processing"

    updated = registry.update_document_status(
        "商务彩铃",
        "abc123",
        status="error",
        error="ingest boom",
    )

    assert updated is True
    doc = registry.list_documents("商务彩铃")[0]
    assert doc["status"] == "error"
    assert doc["error"] == "ingest boom"


def test_update_document_progress_records_stage_and_segment_counts(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("kb")
    registry.register_document(
        "kb",
        file_name="book.pdf",
        file_path="book.pdf",
        sha256="abc",
        status="processing",
    )

    updated = registry.update_document_progress(
        "kb",
        "abc",
        stage="graph_enrichment",
        segments_total=10,
        segments_done=4,
        segments_failed=1,
        partial_errors=["segment 5 timeout"],
    )

    assert updated is True
    doc = registry.list_documents("kb")[0]
    assert doc["stage"] == "graph_enrichment"
    assert doc["segments_total"] == 10
    assert doc["segments_done"] == 4
    assert doc["segments_failed"] == 1
    assert doc["partial_errors"] == ["segment 5 timeout"]


def test_update_document_status_preserves_progress_metadata(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("kb")
    registry.register_document(
        "kb",
        file_name="book.pdf",
        file_path="book.pdf",
        sha256="abc",
        status="processing",
    )
    registry.update_document_progress(
        "kb", "abc", stage="graph_enrichment", segments_total=3
    )

    registry.update_document_status(
        "kb", "abc", status="partial_success", error="1 segment failed"
    )

    doc = registry.list_documents("kb")[0]
    assert doc["status"] == "partial_success"
    assert doc["stage"] == "graph_enrichment"
    assert doc["segments_total"] == 3
    assert doc["error"] == "1 segment failed"
