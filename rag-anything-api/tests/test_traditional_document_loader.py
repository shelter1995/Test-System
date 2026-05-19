from pathlib import Path

import pytest

from rag_engines.traditional.document_loader import UnsupportedDocumentType, load_document_text


def test_load_markdown_text(tmp_path: Path):
    path = tmp_path / "guide.md"
    path.write_text("# 开通指南\n\n提交资料后等待受理。", encoding="utf-8")

    result = load_document_text(path)

    assert result.text == "# 开通指南\n\n提交资料后等待受理。"
    assert result.metadata["file_name"] == "guide.md"
    assert result.metadata["extension"] == ".md"


def test_load_csv_text(tmp_path: Path):
    path = tmp_path / "pricing.csv"
    path.write_text("产品,价格\n商务彩铃,100元/月\n", encoding="utf-8")

    result = load_document_text(path)

    assert "产品,价格" in result.text
    assert "商务彩铃,100元/月" in result.text


def test_reject_unsupported_binary(tmp_path: Path):
    path = tmp_path / "image.png"
    path.write_bytes(b"not an image")

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "不支持传统 RAG 直接处理" in str(exc.value)
