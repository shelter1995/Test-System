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


def test_parse_with_mineru_returns_parsed_document_on_success(monkeypatch, tmp_path: Path):
    source = tmp_path / "a.pdf"
    source.write_bytes(b"%PDF")

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        out_idx = cmd.index("--output-dir") + 1
        out_dir = Path(cmd[out_idx])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.md").write_text("# 标题\n正文", encoding="utf-8")
        return _Result()

    monkeypatch.setattr("rag_engines.traditional.document_parsers.mineru_parser.subprocess.run", _fake_run)

    parsed = parse_with_mineru(source, output_root=tmp_path / "output", mineru_path="mineru")

    assert isinstance(parsed, ParsedDocument)
    assert "正文" in parsed.text
    assert parsed.metadata["parser"] == "mineru"
