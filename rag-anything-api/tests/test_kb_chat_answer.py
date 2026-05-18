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
            "file_name": "资费说明.pdf",
            "snippet": "商务彩铃基础版 10 元/月/线。",
            "score": 0.9,
        }
    ]
