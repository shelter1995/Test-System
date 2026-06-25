from pathlib import Path


def test_knowledge_page_maps_retrying_stage_to_chinese_label():
    source = Path("ai-tutor-system/static/js/knowledge.js").read_text(encoding="utf-8")

    assert "'retrying': '重试解析中'" in source
