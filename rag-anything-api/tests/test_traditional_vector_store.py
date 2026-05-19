from pathlib import Path

from rag_engines.traditional.vector_store import TraditionalVectorStore


def test_upsert_and_search_chunks(tmp_path: Path):
    store = TraditionalVectorStore(tmp_path / "kb.sqlite")
    store.upsert_chunks(
        database="kb",
        document_sha256="sha",
        chunks=[
            {
                "text": "商务彩铃支持企业欢迎语配置。",
                "embedding": [1.0, 0.0, 0.0],
                "metadata": {"source": "guide.md", "chunk_index": 0},
            },
            {
                "text": "售后服务包括工单跟踪。",
                "embedding": [0.0, 1.0, 0.0],
                "metadata": {"source": "service.md", "chunk_index": 1},
            },
        ],
    )

    results = store.search(database="kb", query_embedding=[0.9, 0.1, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0]["text"] == "商务彩铃支持企业欢迎语配置。"
    assert results[0]["metadata"]["source"] == "guide.md"
    assert results[0]["score"] > 0.9


def test_delete_document_removes_chunks(tmp_path: Path):
    store = TraditionalVectorStore(tmp_path / "kb.sqlite")
    store.upsert_chunks(
        database="kb",
        document_sha256="sha",
        chunks=[
            {"text": "内容", "embedding": [1.0, 0.0], "metadata": {"source": "a.md", "chunk_index": 0}},
        ],
    )

    deleted = store.delete_document(database="kb", document_sha256="sha")

    assert deleted == 1
    assert store.search(database="kb", query_embedding=[1.0, 0.0], top_k=5) == []
