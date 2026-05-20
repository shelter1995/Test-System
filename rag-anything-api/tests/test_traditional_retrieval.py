from rag_engines.traditional.retrieval import (
    RetrievalConfig,
    apply_rerank_order,
    assign_source_ids,
    build_rewrite_queries,
    dedupe_candidates,
    filter_candidates,
)


def test_retrieval_config_defaults_are_stable():
    config = RetrievalConfig()
    assert config.min_score == 0.25
    assert config.candidates == 20
    assert config.final_contexts == 8
    assert config.rewrite_enabled is True
    assert config.max_rewrite_queries == 3


def test_build_rewrite_queries_respects_toggle_and_limit():
    query = "商务彩铃开通，价格说明，办理流程"
    disabled = build_rewrite_queries(query, rewrite_enabled=False, max_rewrite_queries=5)
    assert disabled == [query]

    enabled = build_rewrite_queries(query, rewrite_enabled=True, max_rewrite_queries=2)
    assert enabled[0] == query
    assert len(enabled) == 2
    assert len(set(enabled)) == len(enabled)


def test_dedupe_candidates_prefers_higher_score_for_same_chunk():
    candidates = [
        {
            "text": "A-low",
            "score": 0.61,
            "metadata": {"document_sha256": "doc-a", "chunk_index": 0},
        },
        {
            "text": "A-high",
            "score": 0.92,
            "metadata": {"document_sha256": "doc-a", "chunk_index": 0},
        },
        {
            "text": "B",
            "score": 0.75,
            "metadata": {"document_sha256": "doc-b", "chunk_index": 1},
        },
    ]

    deduped = dedupe_candidates(candidates)
    assert len(deduped) == 2
    assert deduped[0]["text"] == "A-high"
    assert deduped[1]["text"] == "B"


def test_filter_candidates_drops_items_below_threshold():
    candidates = [
        {"text": "A", "score": 0.2, "metadata": {}},
        {"text": "B", "score": 0.5, "metadata": {}},
        {"text": "C", "score": 0.8, "metadata": {}},
    ]

    filtered = filter_candidates(candidates, min_score=0.5)
    assert [item["text"] for item in filtered] == ["B", "C"]


def test_apply_rerank_order_reorders_and_keeps_unranked_tail():
    candidates = [
        {"text": "A", "score": 0.9, "metadata": {}},
        {"text": "B", "score": 0.8, "metadata": {}},
        {"text": "C", "score": 0.7, "metadata": {}},
    ]
    rerank = [
        {"index": 2, "relevance_score": 0.95},
        {"index": 0, "relevance_score": 0.91},
    ]

    ordered = apply_rerank_order(candidates, rerank)
    assert [item["text"] for item in ordered] == ["C", "A", "B"]
    assert ordered[0]["rerank_score"] == 0.95
    assert ordered[1]["rerank_score"] == 0.91


def test_assign_source_ids_assigns_human_readable_sequence():
    candidates = [
        {"text": "A", "score": 0.9, "metadata": {}},
        {"text": "B", "score": 0.8, "metadata": {}},
    ]
    assigned = assign_source_ids(candidates)
    assert assigned[0]["source_id"] == "来源 1"
    assert assigned[1]["source_id"] == "来源 2"
