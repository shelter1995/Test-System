import json
from pathlib import Path

from database_registry import DatabaseRegistry
from storage_audit import audit_database_storage


def test_audit_reports_unregistered_lightrag_sources(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database(
        "kb",
        working_dir=str(tmp_path / "storage" / "kb" / "rag_storage"),
        output_dir=str(tmp_path / "output" / "kb"),
    )
    registered_file = tmp_path / "files" / "kb" / "registered.pdf"
    registered_file.parent.mkdir(parents=True)
    registered_file.write_bytes(b"registered")
    registry.register_document(
        "kb",
        file_name="registered.pdf",
        file_path=str(registered_file),
        sha256="sha-registered",
        status="已导入",
    )

    working_dir = tmp_path / "storage" / "kb" / "rag_storage"
    working_dir.mkdir(parents=True)
    (working_dir / "kv_store_text_chunks.json").write_text(
        json.dumps(
            {
                "chunk-1": {"content": "registered text", "file_path": "registered.pdf"},
                "chunk-2": {"content": "orphan text", "file_path": "orphan.pdf"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = audit_database_storage(registry, "kb")

    assert report["database"] == "kb"
    assert report["registered_documents"] == 1
    assert report["orphan_sources"] == ["orphan.pdf"]
    assert report["missing_registered_files"] == []
    assert report["contaminated"] is True
