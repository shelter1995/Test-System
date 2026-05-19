from pathlib import Path

import pytest

from rag_engines.traditional.engine import TraditionalRAGEngine


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
