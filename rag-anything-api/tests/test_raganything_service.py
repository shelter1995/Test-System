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
