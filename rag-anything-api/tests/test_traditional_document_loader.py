import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from rag_engines.traditional.document_loader import (
    UnsupportedDocumentType,
    _resolve_media_runtime_config,
    _resolve_mineru_runtime_config,
    load_document_text,
)
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


def test_pdf_falls_back_to_pypdf_text_when_mineru_unavailable(monkeypatch, tmp_path: Path):
    path = tmp_path / "brochure.pdf"
    path.write_bytes(b"%PDF")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader._read_pdf",
        lambda p: ("宣传册基础文本", 2),
    )
    monkeypatch.setattr("rag_engines.traditional.document_loader.should_use_mineru_for_pdf", lambda text, page_count: True)

    def _raise(**kwargs):
        raise ParserUnavailable("MinerU CLI not configured.")

    monkeypatch.setattr("rag_engines.traditional.document_loader.parse_with_mineru", _raise)

    result = load_document_text(path)

    assert result.text == "宣传册基础文本"
    assert result.metadata["parser"] == "pypdf_fallback"
    assert "增强解析组件" in result.metadata["warning"]


def test_empty_scanned_pdf_without_mineru_reports_chinese_dependency_hint(monkeypatch, tmp_path: Path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF")

    monkeypatch.setattr("rag_engines.traditional.document_loader._read_pdf", lambda p: ("", 1))
    monkeypatch.setattr("rag_engines.traditional.document_loader.should_use_mineru_for_pdf", lambda text, page_count: True)

    def _raise(**kwargs):
        raise ParserUnavailable("MinerU CLI not configured.")

    monkeypatch.setattr("rag_engines.traditional.document_loader.parse_with_mineru", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "增强解析组件" in str(exc.value)
    assert "MinerU CLI not configured" not in str(exc.value)


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


def test_mineru_runtime_config_prefers_python_module_command(monkeypatch, tmp_path: Path):
    command = ["portable-python.exe", "-m", "mineru.cli.client"]
    fake_config = SimpleNamespace(
        RAGANYTHING_OUTPUT_ROOT=tmp_path / "output",
        MINERU_COMMAND=command,
        MINERU_CLI_PATH="",
        MINERU_PATH="",
    )
    monkeypatch.setitem(sys.modules, "config", fake_config)

    output_root, resolved = _resolve_mineru_runtime_config()

    assert output_root == tmp_path / "output" / "traditional_parser"
    assert resolved == command


def test_media_runtime_config_redetects_whisper_after_optional_install(monkeypatch, tmp_path: Path):
    fake_config = SimpleNamespace(
        FFMPEG_PATH="C:/tools/ffmpeg.exe",
        WHISPER_AVAILABLE=False,
        TRADITIONAL_PARSER_DEPENDENCIES={
            "ffmpeg": {"available": True, "path": "C:/tools/ffmpeg.exe"},
            "whisper": {"available": False, "path": ""},
        },
        RAGANYTHING_OUTPUT_ROOT=tmp_path,
    )
    monkeypatch.setitem(sys.modules, "config", fake_config)
    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.detect_traditional_parser_dependencies",
        lambda: {
            "ffmpeg": {"available": True, "path": "C:/tools/ffmpeg.exe"},
            "libreoffice": {"available": False, "path": ""},
            "mineru": {"available": False, "path": ""},
            "whisper": {"available": True, "path": "C:/Data/runtime/optional-site-packages/whisper/__init__.py"},
        },
    )

    ffmpeg_path, whisper_available, output_root = _resolve_media_runtime_config()

    assert ffmpeg_path == "C:/tools/ffmpeg.exe"
    assert whisper_available is True
    assert output_root == tmp_path / "traditional_parser" / "media"


def test_video_transcription_runtime_error_is_not_misreported_as_missing_whisper(monkeypatch, tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video")

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader._resolve_media_runtime_config",
        lambda: ("C:/tools/ffmpeg.exe", True, tmp_path / "media"),
    )

    def _raise(*args, **kwargs):
        raise DocumentParsingError("Whisper transcription failed: Failed to load audio")

    monkeypatch.setattr("rag_engines.traditional.document_loader.transcribe_video", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    message = str(exc.value)
    assert "Whisper transcription failed" in message
    assert "当前基础版未安装" not in message


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
    captured: dict[str, str] = {}

    def _fake_transcribe_audio(file_path, whisper_available, ffmpeg_path=None):
        captured["ffmpeg_path"] = str(ffmpeg_path)
        return "音频转写结果"

    monkeypatch.setattr(
        "rag_engines.traditional.document_loader.transcribe_audio",
        _fake_transcribe_audio,
    )

    result = load_document_text(path)

    assert result.text == "音频转写结果"
    assert result.metadata["extension"] == ".mp3"
    assert "ffmpeg_path" in captured


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


def test_video_missing_ffmpeg_reports_chinese_dependency_hint(monkeypatch, tmp_path: Path):
    path = tmp_path / "demo.mp4"
    path.write_bytes(b"video")

    def _raise(*_args, **_kwargs):
        raise ParserUnavailable("ffmpeg is not available.")

    monkeypatch.setattr("rag_engines.traditional.document_loader.transcribe_video", _raise)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    message = str(exc.value)
    assert "视频解析需要 FFmpeg" in message
    assert "增强解析组件" in message
    assert "ffmpeg is not available" not in message
