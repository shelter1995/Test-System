import asyncio
import time
from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        await asyncio.sleep(0.1)
        return f"{question}:{mode}"


def test_query_all_runs_databases_concurrently(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("库A")
    registry.register_database("库B")
    registry.register_database("库C")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: FakeRAG(),
        query_timeout=1.0,
    )

    start = time.perf_counter()
    result = asyncio.run(service.query_all("资费", mode="naive", n_results=3))
    elapsed = time.perf_counter() - start

    assert result["total_found"] == 3
    assert elapsed < 0.2


class SlowRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        await asyncio.sleep(0.2)
        return "slow"


class FastRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="hybrid"):
        return "fast"


def test_query_all_keeps_fast_results_when_one_database_times_out(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("慢库")
    registry.register_database("快库")

    def factory(db_id, _wd):
        return SlowRAG() if db_id == "慢库" else FastRAG()

    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=factory,
        query_timeout=0.05,
    )

    result = asyncio.run(service.query_all("资费", mode="naive", n_results=5))

    assert result["total_found"] == 1
    assert result["results"][0]["text"] == "fast"
    assert result["errors"][0]["database"] == "慢库"
    assert "timeout" in result["errors"][0]["error"].lower()
