from rag_engines.contracts import ContextResult, IngestResult, SearchResult


def test_ingest_result_payload_is_serializable():
    result = IngestResult(
        status="success",
        database="kb",
        document_sha256="abc",
        file_name="doc.md",
        engine="traditional",
        chunk_count=3,
        message="文档已导入",
    )

    assert result.to_dict() == {
        "status": "success",
        "database": "kb",
        "document_sha256": "abc",
        "file_name": "doc.md",
        "engine": "traditional",
        "chunk_count": 3,
        "message": "文档已导入",
        "error": "",
    }


def test_search_result_payload_contains_sources_and_scores():
    result = SearchResult(
        query="怎么开通",
        database="kb",
        results=[
            {
                "text": "开通步骤包括提交资料并确认业务受理。",
                "score": 0.82,
                "metadata": {"source": "guide.md", "database": "kb"},
            }
        ],
        fallback="",
    )

    payload = result.to_dict()

    assert payload["total_found"] == 1
    assert payload["results"][0]["metadata"]["source"] == "guide.md"
    assert payload["results"][0]["score"] == 0.82


def test_context_result_limits_context_text():
    result = ContextResult(
        query="资费",
        database="kb",
        contexts=[
            {
                "text": "商务彩铃资费按套餐配置。",
                "score": 0.91,
                "metadata": {"source": "pricing.md"},
            }
        ],
        fallback="",
    )

    payload = result.to_dict()

    assert payload["total_found"] == 1
    assert payload["contexts"][0]["text"] == "商务彩铃资费按套餐配置。"
