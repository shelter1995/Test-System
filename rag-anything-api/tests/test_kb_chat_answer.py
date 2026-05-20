from kb_answer import build_kb_answer_prompt, extract_source_summaries


def test_build_kb_answer_prompt_requires_grounded_answer():
    prompt = build_kb_answer_prompt(
        query="资费是多少",
        contexts=[
            {
                "text": "商务彩铃基础版 10 元/月/线。",
                "metadata": {"source": "资费说明.pdf", "database": "kb"},
                "score": 0.92,
            }
        ],
        history=[{"q": "能办理吗", "a": "可以办理"}],
    )

    assert "只能基于【知识库资料】回答" in prompt
    assert "资料不足时回答：当前知识库未找到相关资料" in prompt
    assert "商务彩铃基础版 10 元/月/线" in prompt
    assert "历史对话" in prompt


def test_build_kb_answer_prompt_empty_contexts():
    prompt = build_kb_answer_prompt(query="资费是多少", contexts=[], history=[])
    assert "未检索到可用资料。" in prompt


def test_extract_source_summaries_deduplicates_sources():
    sources = extract_source_summaries(
        [
            {
                "text": "商务彩铃基础版 10 元/月/线。",
                "metadata": {"source": "资费说明.pdf"},
                "score": 0.9,
            },
            {
                "text": "商务彩铃基础版 10 元/月/线。",
                "metadata": {"source": "资费说明.pdf"},
                "score": 0.8,
            },
        ]
    )

    assert sources == [
        {
            "source_id": "",
            "file_name": "资费说明.pdf",
            "snippet": "商务彩铃基础版 10 元/月/线。",
            "score": 0.9,
            "rerank_score": None,
            "chunk_index": None,
            "document_sha256": "",
            "engine": "",
        }
    ]


def test_extract_source_summaries_ctx_not_dict():
    sources = extract_source_summaries(["not a dict", {"text": "valid", "metadata": {"source": "a.pdf"}}])
    assert len(sources) == 1
    assert sources[0]["file_name"] == "a.pdf"


def test_extract_source_summaries_metadata_not_dict():
    sources = extract_source_summaries([{"text": "valid", "metadata": "bad", "score": 0.5}])
    assert len(sources) == 1
    assert sources[0]["file_name"] == "知识库资料"
    assert sources[0]["score"] == 0.5


def test_extract_source_summaries_empty_or_none_text():
    sources = extract_source_summaries([
        {"text": "", "metadata": {"source": "a.pdf"}},
        {"text": None, "metadata": {"source": "b.pdf"}},
        {"text": "   ", "metadata": {"source": "c.pdf"}},
        {"text": "valid text", "metadata": {"source": "d.pdf"}},
    ])
    assert len(sources) == 1
    assert sources[0]["file_name"] == "d.pdf"


def test_extract_source_summaries_max_items_truncation():
    contexts = [{"text": f"text {i}", "metadata": {"source": f"{i}.pdf"}, "score": i / 10} for i in range(10)]
    sources = extract_source_summaries(contexts, max_items=3)
    assert len(sources) == 3


def test_extract_source_summaries_default_fallback_no_source_no_file_path():
    sources = extract_source_summaries([{"text": "content", "metadata": {"database": "kb"}, "score": 0.7}])
    assert len(sources) == 1
    assert sources[0]["file_name"] == "知识库资料"
