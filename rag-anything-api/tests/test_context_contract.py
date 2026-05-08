import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

import app as rag_api
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class ContextRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="naive", **kwargs):
        assert kwargs.get("only_need_context") is True
        return "第一段知识\n第二段知识\n第三段知识"


def test_query_context_returns_trimmed_context_payload(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: ContextRAG(),
    )

    result = asyncio.run(service.query_context("商务彩铃", "资费", mode="naive", max_chars=8))

    assert result["query"] == "资费"
    assert result["database"] == "商务彩铃"
    assert result["total_found"] == 1
    assert len(result["contexts"]) == 1
    assert result["contexts"][0]["text"].startswith("第一段知")
    assert len(result["contexts"][0]["text"]) == 8


class FakeContextService:
    async def query_context(self, database_id, query, mode="naive", max_chars=2000):
        return {
            "query": query,
            "database": database_id,
            "contexts": [
                {
                    "text": "商务彩铃上下文",
                    "metadata": {"source": "raganything", "database": database_id, "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }


def test_context_endpoint_contract(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FakeContextService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.post("/context", json={"query": "资费", "database": "商务彩铃", "n_results": 3})

    assert response.status_code == 200
    assert response.json()["contexts"][0]["text"] == "商务彩铃上下文"
