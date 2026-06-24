import subprocess
from pathlib import Path

import pytest

from rag_engines.traditional.document_parsers import (
    DocumentParsingError,
    ParsedDocument,
    ParserUnavailable,
    parse_with_mineru,
    should_use_mineru_for_pdf,
)


def test_should_use_mineru_for_pdf_when_text_is_too_short():
    assert should_use_mineru_for_pdf("仅有几字", page_count=3) is True


def test_should_use_mineru_for_pdf_when_text_has_high_garbled_ratio():
    text = "正常内容" + ("�" * 20)
    assert should_use_mineru_for_pdf(text, page_count=1) is True


def test_should_use_mineru_for_pdf_when_text_is_sufficient():
    text = "这是可读正文。" * 80
    assert should_use_mineru_for_pdf(text, page_count=2) is False


def test_parse_with_mineru_raises_when_dependency_missing(tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")

    with pytest.raises(ParserUnavailable):
        parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="")


def test_parse_with_mineru_raises_document_parsing_error_on_failed_process(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", lambda *args, **kwargs: _Result())

    with pytest.raises(DocumentParsingError):
        parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")


def test_parse_with_mineru_raises_document_parsing_error_on_timeout(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")
    captured_kwargs = {}

    def _fake_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    with pytest.raises(DocumentParsingError, match="timed out"):
        parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")

    assert captured_kwargs["timeout"] == 30 * 60


def test_parse_with_mineru_returns_parsed_document_on_success(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")
    captured_cmd = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_idx = cmd.index("-o") + 1
        out_dir = Path(cmd[out_idx])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.md").write_text("# 标题\n正文", encoding="utf-8")
        return _Result()

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    parsed = parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")

    assert isinstance(parsed, ParsedDocument)
    assert "正文" in parsed.text
    assert parsed.metadata["parser"] == "mineru"
    assert captured_cmd[:5] == ["mineru", "-p", str(source), "-o", str(tmp_path / "output" / "a_mineru")]
    assert "--input" not in captured_cmd
    assert "--output-dir" not in captured_cmd


def test_parse_with_mineru_uses_pipeline_backend_for_pdfs(monkeypatch, tmp_path: Path):
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF")
    captured_cmd = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.md").write_text("PDF OCR 文本", encoding="utf-8")
        return _Result()

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    parsed = parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")

    assert "PDF OCR 文本" in parsed.text
    assert captured_cmd[captured_cmd.index("-b") + 1] == "pipeline"


def test_parse_with_mineru_accepts_python_module_command(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")
    captured_cmd = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.md").write_text("模块入口解析结果", encoding="utf-8")
        return _Result()

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    parsed = parse_with_mineru(
        source,
        output_root=tmp_path / "output",
        mineru_path=["portable-python.exe", "-m", "mineru.cli.client"],
    )

    assert "模块入口解析结果" in parsed.text
    assert captured_cmd[:3] == ["portable-python.exe", "-m", "mineru.cli.client"]


def test_parse_with_mineru_uses_pipeline_ocr_for_images(monkeypatch, tmp_path: Path):
    source = tmp_path / "long-image.png"
    source.write_bytes(b"png")
    captured_cmd = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        out_dir = Path(cmd[cmd.index("-o") + 1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.md").write_text("图片 OCR 文本", encoding="utf-8")
        return _Result()

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    parsed = parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")

    assert "图片 OCR 文本" in parsed.text
    assert captured_cmd[captured_cmd.index("-m") + 1] == "ocr"
    assert captured_cmd[captured_cmd.index("-b") + 1] == "pipeline"
