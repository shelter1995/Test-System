from pathlib import Path

import pytest

from rag_engines.traditional.document_loader import UnsupportedDocumentType, load_document_text
from rag_engines.traditional.document_parsers import DocumentParsingError, ParsedDocument


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


def test_pdf_routes_to_mineru_when_pdf_text_is_low(monkeypatch, tmp_path: Path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF")
    mineru_doc = ParsedDocument(text="OCR文本", metadata={"parser": "mineru"})

    monkeypatch.setattr("rag_engines.traditional.document_loader._read_pdf", lambda p: ("", 2))
    monkeypatch.setattr("rag_engines.traditional.document_loader.should_use_mineru_for_pdf", lambda text, page_count: True)
    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.parse_with_mineru",
        lambda **kwargs: mineru_doc,
    )

    result = load_document_text(path)

    assert result.text == "OCR文本"
    assert result.metadata["parser"] == "mineru"
    assert result.metadata["extension"] == ".pdf"


def test_pdf_keeps_pypdf_when_text_is_sufficient(monkeypatch, tmp_path: Path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"%PDF")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader._read_pdf",
        lambda p: ("正文内容足够详细" * 20, 1),
    )
    monkeypatch.setattr("rag_engines.traditional.document_loader.should_use_mineru_for_pdf", lambda text, page_count: False)

    result = load_document_text(path)

    assert "正文内容足够详细" in result.text
    assert result.metadata["extension"] == ".pdf"
    assert "parser" not in result.metadata


def test_image_routes_to_mineru(monkeypatch, tmp_path: Path):
    path = tmp_path / "page.png"
    path.write_bytes(b"image")
    mineru_doc = ParsedDocument(text="图片OCR结果", metadata={"parser": "mineru", "source_type": "image"})

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.parse_with_mineru",
        lambda **kwargs: mineru_doc,
    )

    result = load_document_text(path)

    assert result.text == "图片OCR结果"
    assert result.metadata["source_type"] == "image"
    assert result.metadata["extension"] == ".png"


def test_parser_errors_are_mapped_to_unsupported_type(monkeypatch, tmp_path: Path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF")

    monkeypatch.setattr("rag_engines.traditional.document_loader._read_pdf", lambda p: ("", 1))
    monkeypatch.setattr("rag_engines.traditional.document_loader.should_use_mineru_for_pdf", lambda text, page_count: True)

    def _raise(**kwargs):
        raise DocumentParsingError("mineru failed")

    monkeypatch.setattr("rag_engines.traditional.document_loader.parse_with_mineru", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "解析失败" in str(exc.value)
