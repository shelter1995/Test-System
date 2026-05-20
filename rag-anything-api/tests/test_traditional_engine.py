from pathlib import Path

import pytest

from rag_engines.traditional.engine import TraditionalRAGEngine
from rag_engines.traditional.document_loader import UnsupportedDocumentType, load_document_text


class FakeEmbeddingClient:
    async def embed(self, texts):
        vectors = []
        for text in texts:
            if "开通" in text or "开通" == text:
                vectors.append([1.0, 0.0, 0.0])
            elif "价格" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class FakeRerankClient:
    async def rerank(self, query, documents, top_n):
        return [
            {"index": 1, "relevance_score": 0.98},
            {"index": 0, "relevance_score": 0.91},
        ]


@pytest.mark.asyncio
async def test_ingest_and_query_markdown(tmp_path: Path):
    source = tmp_path / "guide.md"
    source.write_text("商务彩铃开通需要提交企业资料。", encoding="utf-8")
    engine = TraditionalRAGEngine(
        storage_root=tmp_path / "storage",
        embedding_client=FakeEmbeddingClient(),
        rerank_client=None,
        chunk_size=200,
        chunk_overlap=20,
    )

    ingest = await engine.ingest_file("kb", source)
    result = await engine.query("kb", "如何开通", n_results=3)

    assert ingest["status"] == "success"
    assert ingest["engine"] == "traditional"
    assert ingest["chunk_count"] == 1
    assert result["total_found"] == 1
    assert "提交企业资料" in result["results"][0]["text"]


@pytest.mark.asyncio
async def test_query_context_respects_max_chars(tmp_path: Path):
    source = tmp_path / "guide.md"
    source.write_text("商务彩铃开通需要提交企业资料，并等待业务受理完成。", encoding="utf-8")
    engine = TraditionalRAGEngine(
        storage_root=tmp_path / "storage",
        embedding_client=FakeEmbeddingClient(),
        rerank_client=None,
        chunk_size=200,
        chunk_overlap=20,
    )

    await engine.ingest_file("kb", source)
    result = await engine.query_context("kb", "开通", max_chars=12)

    assert result["total_found"] == 1
    assert len(result["contexts"][0]["text"]) <= 12


def test_xls_error_explains_xlsx_requirement(tmp_path: Path):
    source = tmp_path / "old.xls"
    source.write_bytes(b"legacy")

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(source)

    message = str(exc.value)
    assert ".xlsx" in message or "LibreOffice" in message


@pytest.mark.asyncio
async def test_retrieve_contexts_applies_multi_query_dedupe_threshold_rerank_and_source_ids(tmp_path: Path, monkeypatch):
    from rag_engines.traditional.retrieval import RetrievalConfig
    import rag_engines.traditional.engine as engine_module

    source_a = tmp_path / "open.md"
    source_a.write_text("开通流程说明。", encoding="utf-8")
    source_b = tmp_path / "price.md"
    source_b.write_text("价格说明。", encoding="utf-8")
    engine = TraditionalRAGEngine(
        storage_root=tmp_path / "storage",
        embedding_client=FakeEmbeddingClient(),
        rerank_client=FakeRerankClient(),
        retrieval_config=RetrievalConfig(
            rewrite_enabled=True,
            max_rewrite_queries=2,
            candidates=3,
            final_contexts=2,
            min_score=0.2,
        ),
        chunk_size=200,
        chunk_overlap=20,
    )
    await engine.ingest_file("kb", source_a)
    await engine.ingest_file("kb", source_b)
    monkeypatch.setattr(engine_module, "build_rewrite_queries", lambda *_args, **_kwargs: ["如何开通", "价格"])

    contexts = await engine.retrieve_contexts("kb", "ignored", enable_rerank=True)

    assert len(contexts) == 2
    assert contexts[0]["metadata"]["source"] == "price.md"
    assert contexts[0]["source_id"] == "来源 1"
    assert contexts[1]["source_id"] == "来源 2"
    assert contexts[0]["metadata"]["document_sha256"]
    assert contexts[0]["metadata"]["chunk_index"] == 0


@pytest.mark.asyncio
async def test_query_context_uses_retrieve_contexts_output(tmp_path: Path, monkeypatch):
    engine = TraditionalRAGEngine(
        storage_root=tmp_path / "storage",
        embedding_client=FakeEmbeddingClient(),
        rerank_client=None,
        chunk_size=200,
        chunk_overlap=20,
    )
    observed = {}

    async def fake_retrieve_contexts(database_id, query, n_results=None, enable_rerank=None):
        observed["database_id"] = database_id
        observed["query"] = query
        observed["n_results"] = n_results
        observed["enable_rerank"] = enable_rerank
        return [{"text": "abcdefgh", "score": 0.8, "source_id": "来源 1", "metadata": {"source": "fake.md"}}]

    monkeypatch.setattr(engine, "retrieve_contexts", fake_retrieve_contexts)

    result = await engine.query_context("kb", "开通", max_chars=4)

    assert observed["database_id"] == "kb"
    assert observed["query"] == "开通"
    assert result["total_found"] == 1
    assert result["contexts"][0]["text"] == "abcd"
    assert result["contexts"][0]["source_id"] == "来源 1"
