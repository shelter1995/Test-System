from rag_engines.traditional.chunking import chunk_text


def test_chunk_text_keeps_source_metadata():
    text = "第一段介绍产品。\n\n第二段介绍开通流程。\n\n第三段介绍售后。"

    chunks = chunk_text(
        text,
        source="guide.md",
        database="kb",
        chunk_size=18,
        chunk_overlap=4,
    )

    assert len(chunks) >= 2
    assert chunks[0]["metadata"]["source"] == "guide.md"
    assert chunks[0]["metadata"]["database"] == "kb"
    assert chunks[0]["metadata"]["chunk_index"] == 0
    assert chunks[0]["text"].strip()


def test_chunk_text_returns_empty_for_blank_input():
    assert chunk_text("  \n\t  ", source="empty.md", database="kb") == []
