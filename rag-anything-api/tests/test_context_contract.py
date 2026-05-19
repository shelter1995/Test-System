import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as rag_api
import config
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(rag_api, "startup_error", None)
    return TestClient(rag_api.app)


class ContextRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="naive", **kwargs):
        assert kwargs.get("only_need_context") is True
        return "第一段知识\n第二段知识\n第三段知识"


class InitFailedRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": False, "error": "vector store broken"}


class NoContextRAG:
    async def _ensure_lightrag_initialized(self):
        return {"success": True}

    async def aquery(self, question, mode="naive", **kwargs):
        return "[no-context] No relevant document chunks found"


def _register_recipe_doc(registry: DatabaseRegistry, tmp_path: Path) -> None:
    source = tmp_path / "中国名菜巴蜀风味.pdf"
    source.write_text("placeholder", encoding="utf-8")
    registry.register_database("COOKer")
    registry.register_document(
        "COOKer",
        file_name="中国名菜巴蜀风味.pdf",
        stored_file_name="中国名菜巴蜀风味.pdf",
        file_path=str(source),
        sha256="recipe",
        source="中国名菜巴蜀风味.pdf",
    )


def _write_recipe_outputs(output_root: Path) -> None:
    cooker = output_root / "COOKer"
    cooker.mkdir(parents=True)
    (cooker / "中国名菜巴蜀风味.md").write_text(
        "## 仔姜田鸡\n## [烹制方法]\n1.将净田鸡腿肉码味；嫩仔姜切片。2.旺火滑炒田鸡腿，加入仔姜、甜椒和葱白炒香。\n\n"
        "## 熊掌豆腐\n做法不同，特点各异，但都是家常味型。",
        encoding="utf-8",
    )
    (cooker / "中国名菜滇黔风味.md").write_text(
        "## 人像摄影\n摆拍时应调整肩线和视线。",
        encoding="utf-8",
    )


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


def test_query_context_uses_registered_local_output_when_init_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_LOCAL_FIRST", False)
    registry = DatabaseRegistry(tmp_path / "databases.json")
    _register_recipe_doc(registry, tmp_path)
    _write_recipe_outputs(tmp_path / "output")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: InitFailedRAG(),
    )

    result = asyncio.run(service.query_context("COOKer", "田鸡有什么做法", mode="naive"))

    assert result["fallback"] == "local_text"
    assert result["fallback_reason"] == "rag_init_failed"
    assert result["contexts"]
    assert "田鸡" in result["contexts"][0]["text"]
    assert all("滇黔" not in ctx["metadata"]["source"] for ctx in result["contexts"])
    assert all("人像摄影" not in ctx["text"] for ctx in result["contexts"])
    assert all("熊掌豆腐" not in ctx["text"] for ctx in result["contexts"])


def test_query_context_uses_local_output_when_rag_returns_no_context(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    _register_recipe_doc(registry, tmp_path)
    _write_recipe_outputs(tmp_path / "output")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda _db, _wd: NoContextRAG(),
    )

    result = asyncio.run(service.query_context("COOKer", "田鸡有什么做法", mode="naive"))

    assert result["fallback"] == "local_text"
    assert result["contexts"]
    assert "田鸡" in result["contexts"][0]["text"]


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
    monkeypatch.setattr(rag_api, "_engine_for_database", lambda db_id: FakeContextService())
    client = TestClient(rag_api.app)

    response = client.post("/context", json={"query": "资费", "database": "商务彩铃", "n_results": 3})

    assert response.status_code == 200
    assert response.json()["contexts"][0]["text"] == "商务彩铃上下文"


def test_context_response_contains_source_metadata(client, monkeypatch):
    class FakeEngine:
        async def query_context(self, database_id, query, mode="naive", max_chars=3000):
            return {
                "query": query,
                "database": database_id,
                "contexts": [
                    {
                        "text": "开通需要提交企业资料。",
                        "score": 0.86,
                        "metadata": {"source": "guide.md", "database": database_id, "engine": "traditional"},
                    }
                ],
                "total_found": 1,
            }

    monkeypatch.setattr(rag_api, "rag_service", FakeContextService())
    monkeypatch.setattr(rag_api, "_engine_for_database", lambda db_id: FakeEngine())

    response = client.post("/context", json={"database": "kb", "query": "怎么开通"})

    assert response.status_code == 200
    item = response.json()["contexts"][0]
    assert item["metadata"]["source"] == "guide.md"
    assert item["metadata"]["engine"] == "traditional"


def test_context_response_always_includes_fallback(client, monkeypatch):
    class NoFallbackEngine:
        async def query_context(self, database_id, query, mode="naive", max_chars=3000):
            return {
                "query": query,
                "database": database_id,
                "contexts": [],
                "total_found": 0,
            }

    monkeypatch.setattr(rag_api, "rag_service", FakeContextService())
    monkeypatch.setattr(rag_api, "_engine_for_database", lambda db_id: NoFallbackEngine())

    response = client.post("/context", json={"database": "kb", "query": "测试"})

    assert response.status_code == 200
    assert "fallback" in response.json()
    assert response.json()["fallback"] == ""
