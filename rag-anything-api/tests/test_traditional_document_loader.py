import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from rag_engines.traditional.document_loader import UnsupportedDocumentType, load_document_text
from rag_engines.traditional.document_parsers import DocumentParsingError, ParsedDocument, ParserUnavailable


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


def test_load_pptx_extracts_title_text_and_table(monkeypatch, tmp_path: Path):
    class _Cell:
        def __init__(self, text: str):
            self.text = text

    class _Row:
        def __init__(self, values: list[str]):
            self.cells = [_Cell(value) for value in values]

    class _Table:
        def __init__(self):
            self.rows = [_Row(["套餐", "价格"]), _Row(["商务彩铃", "100元/月"])]

    class _Shape:
        def __init__(self, text: str = "", has_table: bool = False):
            self.text = text
            self.has_table = has_table
            self.table = _Table() if has_table else None

    class _Slide:
        def __init__(self):
            self.shapes = [_Shape("政企服务"), _Shape("重点产品说明"), _Shape(has_table=True)]

    fake_pptx_module = SimpleNamespace(Presentation=lambda _: SimpleNamespace(slides=[_Slide()]))
    monkeypatch.setitem(sys.modules, "pptx", fake_pptx_module)

    path = tmp_path / "plan.pptx"
    path.write_bytes(b"pptx")
    result = load_document_text(path)

    assert "政企服务" in result.text
    assert "重点产品说明" in result.text
    assert "套餐 | 价格" in result.text
    assert "商务彩铃 | 100元/月" in result.text


def test_legacy_office_converts_then_recurses(monkeypatch, tmp_path: Path):
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"legacy")
    converted = tmp_path / "legacy.docx"
    converted.write_bytes(b"docx")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.convert_with_libreoffice",
        lambda path, output_dir, libreoffice_path: converted,
    )
    monkeypatch.setattr("rag_engines.traditional.document_loader._read_docx", lambda _p: "转换后文档文本")

    result = load_document_text(path)

    assert result.text == "转换后文档文本"
    assert result.metadata["extension"] == ".docx"
    assert result.metadata["file_name"] == "legacy.docx"


def test_legacy_office_missing_libreoffice_maps_to_unsupported(monkeypatch, tmp_path: Path):
    path = tmp_path / "legacy.xls"
    path.write_bytes(b"legacy")

    def _raise(*_args, **_kwargs):
        raise ParserUnavailable("LibreOffice 未安装")

    monkeypatch.setattr("rag_engines.traditional.document_loader.convert_with_libreoffice", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "LibreOffice" in str(exc.value)


def test_audio_routes_to_whisper_transcription(monkeypatch, tmp_path: Path):
    path = tmp_path / "call.mp3"
    path.write_bytes(b"audio")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.transcribe_audio",
        lambda file_path, whisper_available: "音频转写结果",
    )

    result = load_document_text(path)

    assert result.text == "音频转写结果"
    assert result.metadata["extension"] == ".mp3"


def test_video_routes_to_ffmpeg_then_whisper(monkeypatch, tmp_path: Path):
    path = tmp_path / "meeting.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.transcribe_video",
        lambda file_path, output_dir, ffmpeg_path, whisper_available: "视频转写结果",
    )

    result = load_document_text(path)

    assert result.text == "视频转写结果"
    assert result.metadata["extension"] == ".mp4"


def test_media_parser_unavailable_maps_to_unsupported(monkeypatch, tmp_path: Path):
    path = tmp_path / "call.wav"
    path.write_bytes(b"audio")

    def _raise(*_args, **_kwargs):
        raise ParserUnavailable("Whisper not available")

    monkeypatch.setattr("rag_engines.traditional.document_loader.transcribe_audio", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "Whisper" in str(exc.value)
