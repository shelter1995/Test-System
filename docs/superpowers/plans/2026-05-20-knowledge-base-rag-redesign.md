# Knowledge Base RAG Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the visible knowledge-base flow around traditional RAG, add robust document/OCR/media parsing, and improve knowledge-base answers with multi-stage retrieval and source-cited generation.

**Architecture:** Keep `TraditionalRAGEngine` as the user-facing retrieval engine. Add focused parser modules that convert documents, images, audio, and video into text/Markdown before chunking. Add a multi-stage retrieval layer inside the traditional engine, then keep `/kb/chat` compatible while enriching source metadata for the frontend.

**Tech Stack:** FastAPI, Python 3.12/3.13, SQLite, NumPy, pypdf, python-docx, openpyxl, python-pptx, LibreOffice/soffice, MinerU, ffmpeg, openai-whisper, vanilla JavaScript.

---

## File Structure

Create:

- `rag-anything-api/rag_engines/traditional/dependencies.py` — runtime dependency discovery for MinerU, LibreOffice, ffmpeg, and Whisper.
- `rag-anything-api/rag_engines/traditional/document_parsers/__init__.py` — parser package exports.
- `rag-anything-api/rag_engines/traditional/document_parsers/common.py` — parser result dataclass and parser-specific exceptions.
- `rag-anything-api/rag_engines/traditional/document_parsers/office_converter.py` — LibreOffice conversion helper for `.doc`, `.xls`, `.ppt`.
- `rag-anything-api/rag_engines/traditional/document_parsers/mineru_parser.py` — MinerU wrapper for scanned/complex PDFs and image OCR.
- `rag-anything-api/rag_engines/traditional/document_parsers/media_parser.py` — Whisper and ffmpeg helpers for audio/video transcription.
- `rag-anything-api/rag_engines/traditional/retrieval.py` — multi-query retrieval, candidate merge, thresholding, rerank ordering, and source numbering.
- `rag-anything-api/tests/test_traditional_dependencies.py`
- `rag-anything-api/tests/test_traditional_mineru_parser.py`
- `rag-anything-api/tests/test_traditional_media_parser.py`
- `rag-anything-api/tests/test_traditional_retrieval.py`
- `rag-anything-api/tests/test_kb_answer.py`

Modify:

- `rag-anything-api/config.py` — add dependency detection and KB retrieval config.
- `rag-anything-api/app.py` — force new DBs to traditional RAG, enrich `/status`, enrich `/kb/chat` sources.
- `rag-anything-api/database_registry.py` — preserve compatibility while defaulting to traditional.
- `rag-anything-api/rag_engines/factory.py` — pass retrieval config into traditional engine.
- `rag-anything-api/rag_engines/traditional/document_loader.py` — route files through parser modules.
- `rag-anything-api/rag_engines/traditional/engine.py` — use multi-stage retrieval for query context.
- `rag-anything-api/rag_engines/traditional/model_clients.py` — expose chat client usage for query rewrite if needed.
- `rag-anything-api/rag_engines/traditional/vector_store.py` — return chunk index and stable identifiers.
- `rag-anything-api/kb_answer.py` — source IDs and stricter answer prompt.
- `ai-tutor-system/static/js/knowledge.js` — hide engine controls and show full supported formats.
- `ai-tutor-system/static/js/knowledge-chat.js` — render source IDs and richer source metadata.
- `README.md`, `SETUP.md`, `rag_database_guide.md`, `使用说明.md` — update knowledge-base behavior and dependencies.

---

### Task 1: Dependency Discovery and Config

**Files:**
- Create: `rag-anything-api/rag_engines/traditional/dependencies.py`
- Modify: `rag-anything-api/config.py`
- Modify: `rag-anything-api/app.py`
- Test: `rag-anything-api/tests/test_traditional_dependencies.py`

- [ ] **Step 1: Write the failing dependency tests**

Add `rag-anything-api/tests/test_traditional_dependencies.py`:

```python
import types

from rag_engines.traditional.dependencies import detect_traditional_parser_dependencies


def test_detect_dependencies_reports_available_tools(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"C:/bin/{name}.exe" if name in {"ffmpeg", "soffice", "mineru"} else None)
    monkeypatch.setattr("rag_engines.traditional.dependencies.find_spec", lambda name: object() if name == "whisper" else None)

    deps = detect_traditional_parser_dependencies()

    assert deps["ffmpeg"]["available"] is True
    assert deps["libreoffice"]["available"] is True
    assert deps["mineru"]["available"] is True
    assert deps["whisper"]["available"] is True
    assert deps["libreoffice"]["path"].endswith("soffice.exe")


def test_detect_dependencies_reports_missing_tools(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("rag_engines.traditional.dependencies.find_spec", lambda name: None)

    deps = detect_traditional_parser_dependencies()

    assert deps["ffmpeg"]["available"] is False
    assert deps["libreoffice"]["available"] is False
    assert deps["mineru"]["available"] is False
    assert deps["whisper"]["available"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_dependencies.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag_engines.traditional.dependencies'`.

- [ ] **Step 3: Implement dependency discovery**

Create `rag-anything-api/rag_engines/traditional/dependencies.py`:

```python
from __future__ import annotations

from importlib.util import find_spec
import shutil
from typing import Any


def _tool_status(name: str, path: str | None, label: str | None = None) -> dict[str, Any]:
    return {
        "name": label or name,
        "available": bool(path),
        "path": path or "",
    }


def detect_traditional_parser_dependencies() -> dict[str, dict[str, Any]]:
    ffmpeg_path = shutil.which("ffmpeg")
    soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
    mineru_path = shutil.which("mineru")
    whisper_available = find_spec("whisper") is not None
    return {
        "ffmpeg": _tool_status("ffmpeg", ffmpeg_path),
        "libreoffice": _tool_status("soffice", soffice_path, label="LibreOffice"),
        "mineru": _tool_status("mineru", mineru_path),
        "whisper": {
            "name": "openai-whisper",
            "available": whisper_available,
            "path": "python-package" if whisper_available else "",
        },
    }
```

In `rag-anything-api/config.py`, import and expose:

```python
from rag_engines.traditional.dependencies import detect_traditional_parser_dependencies

TRADITIONAL_PARSER_DEPENDENCIES = detect_traditional_parser_dependencies()
LIBREOFFICE_PATH = TRADITIONAL_PARSER_DEPENDENCIES["libreoffice"]["path"]
MINERU_CLI_PATH = TRADITIONAL_PARSER_DEPENDENCIES["mineru"]["path"]

KB_QUERY_REWRITE_ENABLED = _safe_bool(os.getenv("KB_QUERY_REWRITE_ENABLED"), True)
KB_RETRIEVAL_CANDIDATES = _safe_int(os.getenv("KB_RETRIEVAL_CANDIDATES", "20"), 20)
KB_FINAL_CONTEXTS = _safe_int(os.getenv("KB_FINAL_CONTEXTS", "8"), 8)
KB_MIN_SCORE = _safe_float(os.getenv("KB_MIN_SCORE", "0.2"), 0.2)
KB_MAX_REWRITE_QUERIES = _safe_int(os.getenv("KB_MAX_REWRITE_QUERIES", "3"), 3)
```

In `/status` in `rag-anything-api/app.py`, add:

```python
"traditional_parser": config.TRADITIONAL_PARSER_DEPENDENCIES,
```

- [ ] **Step 4: Run the dependency tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_dependencies.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rag-anything-api\rag_engines\traditional\dependencies.py rag-anything-api\config.py rag-anything-api\app.py rag-anything-api\tests\test_traditional_dependencies.py
git commit -m "feat: expose traditional parser dependencies"
```

---

### Task 2: Parser Contracts, MinerU Routing, and Image OCR

**Files:**
- Create: `rag-anything-api/rag_engines/traditional/document_parsers/__init__.py`
- Create: `rag-anything-api/rag_engines/traditional/document_parsers/common.py`
- Create: `rag-anything-api/rag_engines/traditional/document_parsers/mineru_parser.py`
- Modify: `rag-anything-api/rag_engines/traditional/document_loader.py`
- Test: `rag-anything-api/tests/test_traditional_mineru_parser.py`
- Test: `rag-anything-api/tests/test_traditional_document_loader.py`

- [ ] **Step 1: Write failing parser tests**

Add `rag-anything-api/tests/test_traditional_mineru_parser.py`:

```python
from pathlib import Path

import pytest

from rag_engines.traditional.document_parsers.common import ParserUnavailable
from rag_engines.traditional.document_parsers.mineru_parser import (
    should_use_mineru_for_pdf,
    parse_with_mineru,
)


def test_should_use_mineru_for_pdf_when_text_is_too_short():
    assert should_use_mineru_for_pdf("少量文字", page_count=5) is True


def test_should_not_use_mineru_for_text_pdf_with_enough_text():
    text = "商务彩铃开通流程。" * 200
    assert should_use_mineru_for_pdf(text, page_count=2) is False


def test_should_use_mineru_for_garbled_pdf_text():
    garbled = "\ufffd" * 80 + "abc" * 5
    assert should_use_mineru_for_pdf(garbled, page_count=1) is True


def test_parse_with_mineru_requires_dependency(tmp_path: Path):
    image = tmp_path / "scan.png"
    image.write_bytes(b"fake image")

    with pytest.raises(ParserUnavailable) as exc:
        parse_with_mineru(image, output_root=tmp_path / "cache", mineru_path="")

    assert "MinerU" in str(exc.value)
```

Extend `rag-anything-api/tests/test_traditional_document_loader.py`:

```python
def test_image_requires_mineru_when_ocr_dependency_missing(tmp_path: Path, monkeypatch):
    source = tmp_path / "scan.png"
    source.write_bytes(b"fake image")
    monkeypatch.setattr("rag_engines.traditional.document_loader.config.MINERU_CLI_PATH", "")

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(source)

    assert "MinerU" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_mineru_parser.py rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: FAIL because `document_parsers` and MinerU routing do not exist.

- [ ] **Step 3: Implement parser contract and MinerU wrapper**

Create `rag-anything-api/rag_engines/traditional/document_parsers/common.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ParserUnavailable(RuntimeError):
    pass


class DocumentParsingError(RuntimeError):
    pass


@dataclass
class ParsedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

Create `rag-anything-api/rag_engines/traditional/document_parsers/__init__.py`:

```python
from .common import DocumentParsingError, ParsedDocument, ParserUnavailable

__all__ = ["DocumentParsingError", "ParsedDocument", "ParserUnavailable"]
```

Create `rag-anything-api/rag_engines/traditional/document_parsers/mineru_parser.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import ParsedDocument, ParserUnavailable, DocumentParsingError


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def should_use_mineru_for_pdf(text: str, page_count: int) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return True
    min_chars = max(300, int(page_count or 1) * 120)
    replacement_count = clean.count("\ufffd")
    garbled_ratio = replacement_count / max(1, len(clean))
    return len(clean) < min_chars or garbled_ratio > 0.05


def _read_first_markdown(output_dir: Path) -> str:
    markdown_files = sorted(output_dir.rglob("*.md"))
    if not markdown_files:
        return ""
    return "\n\n".join(path.read_text(encoding="utf-8", errors="replace") for path in markdown_files)


def parse_with_mineru(path: str | Path, output_root: str | Path, mineru_path: str) -> ParsedDocument:
    source = Path(path)
    if not mineru_path:
        raise ParserUnavailable(f"当前环境未检测到 MinerU，无法解析 {source.suffix} 文件。请安装 MinerU 或上传可直接抽取文本的文件。")

    output_dir = Path(output_root) / source.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [mineru_path, "-p", str(source), "-o", str(output_dir)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    except OSError as exc:
        raise ParserUnavailable(f"MinerU 启动失败: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DocumentParsingError(f"MinerU 解析超时: {source.name}") from exc

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise DocumentParsingError(f"MinerU 解析失败: {message or source.name}")

    markdown = _read_first_markdown(output_dir).strip()
    if not markdown:
        raise DocumentParsingError(f"MinerU 未输出可索引文本: {source.name}")
    return ParsedDocument(text=markdown, metadata={"parser": "mineru", "mineru_output_dir": str(output_dir)})
```

- [ ] **Step 4: Route images and scanned PDFs in document loader**

In `rag-anything-api/rag_engines/traditional/document_loader.py`, import:

```python
import config
from .document_parsers.common import ParserUnavailable, DocumentParsingError
from .document_parsers.mineru_parser import IMAGE_EXTENSIONS, parse_with_mineru, should_use_mineru_for_pdf
```

Change `_read_pdf` to return page count:

```python
def _read_pdf(path: Path) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[第 {index + 1} 页]\n{text.strip()}")
    return "\n\n".join(pages), len(reader.pages)
```

In `load_document_text`, replace the PDF and image branches:

```python
    metadata_extra = {}
    try:
        if extension in {".txt", ".md"}:
            text = _read_text_file(file_path)
        elif extension == ".csv":
            text = _read_csv(file_path)
        elif extension == ".pdf":
            text, page_count = _read_pdf(file_path)
            if should_use_mineru_for_pdf(text, page_count=page_count):
                parsed = parse_with_mineru(
                    file_path,
                    output_root=config.TRADITIONAL_RAG_STORAGE_ROOT / "parser_cache",
                    mineru_path=config.MINERU_CLI_PATH,
                )
                text = parsed.text
                metadata_extra.update(parsed.metadata)
        elif extension in IMAGE_EXTENSIONS:
            parsed = parse_with_mineru(
                file_path,
                output_root=config.TRADITIONAL_RAG_STORAGE_ROOT / "parser_cache",
                mineru_path=config.MINERU_CLI_PATH,
            )
            text = parsed.text
            metadata_extra.update(parsed.metadata)
```

In the exception block, translate parser errors:

```python
    except (ParserUnavailable, DocumentParsingError) as exc:
        raise UnsupportedDocumentType(str(exc)) from exc
```

When returning metadata, merge `metadata_extra`:

```python
        metadata={
            "file_name": file_path.name,
            "extension": extension,
            "path": str(file_path),
            **{key: str(value) for key, value in metadata_extra.items()},
        },
```

- [ ] **Step 5: Run parser tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_mineru_parser.py rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rag-anything-api\rag_engines\traditional\document_parsers rag-anything-api\rag_engines\traditional\document_loader.py rag-anything-api\tests\test_traditional_mineru_parser.py rag-anything-api\tests\test_traditional_document_loader.py
git commit -m "feat: add mineru routing for pdf and image parsing"
```

---

### Task 3: PPTX and Legacy Office Conversion

**Files:**
- Create: `rag-anything-api/rag_engines/traditional/document_parsers/office_converter.py`
- Modify: `rag-anything-api/rag_engines/traditional/document_loader.py`
- Test: `rag-anything-api/tests/test_traditional_document_loader.py`

- [ ] **Step 1: Write failing tests for PPTX and legacy Office errors**

Extend `rag-anything-api/tests/test_traditional_document_loader.py`:

```python
def test_pptx_text_is_loaded(tmp_path: Path):
    from pptx import Presentation

    path = tmp_path / "deck.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "商务彩铃方案"
    textbox = slide.shapes.add_textbox(0, 0, 3000000, 500000)
    textbox.text_frame.text = "办理流程和资费说明"
    prs.save(path)

    result = load_document_text(path)

    assert "商务彩铃方案" in result.text
    assert "办理流程和资费说明" in result.text
    assert result.metadata["extension"] == ".pptx"


@pytest.mark.parametrize("suffix", [".doc", ".xls", ".ppt"])
def test_legacy_office_requires_libreoffice(tmp_path: Path, monkeypatch, suffix: str):
    path = tmp_path / f"legacy{suffix}"
    path.write_bytes(b"legacy office")
    monkeypatch.setattr("rag_engines.traditional.document_loader.config.LIBREOFFICE_PATH", "")

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(path)

    assert "LibreOffice" in str(exc.value)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: FAIL because `.pptx` and legacy Office conversion are unsupported.

- [ ] **Step 3: Implement Office converter and PPTX reader**

Create `rag-anything-api/rag_engines/traditional/document_parsers/office_converter.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import DocumentParsingError, ParserUnavailable


LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}


def convert_with_libreoffice(path: str | Path, output_dir: str | Path, libreoffice_path: str) -> Path:
    source = Path(path)
    if not libreoffice_path:
        raise ParserUnavailable(
            f"当前环境未检测到 LibreOffice，无法解析 {source.suffix} 文件。请安装 LibreOffice 或另存为新版 Office 格式后上传。"
        )

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    convert_to = {
        ".doc": "docx",
        ".xls": "xlsx",
        ".ppt": "pptx",
    }.get(source.suffix.lower())
    if not convert_to:
        raise DocumentParsingError(f"不支持的 Office 转换格式: {source.suffix}")

    command = [
        libreoffice_path,
        "--headless",
        "--convert-to",
        convert_to,
        "--outdir",
        str(target_dir),
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise DocumentParsingError(f"LibreOffice 转换失败: {message or source.name}")

    converted = target_dir / f"{source.stem}.{convert_to}"
    if not converted.exists():
        matches = sorted(target_dir.glob(f"{source.stem}.*"))
        if matches:
            return matches[0]
        raise DocumentParsingError(f"LibreOffice 未生成转换文件: {source.name}")
    return converted
```

In `document_loader.py`, add:

```python
from .document_parsers.office_converter import LEGACY_OFFICE_EXTENSIONS, convert_with_libreoffice
```

Add `_read_pptx`:

```python
def _read_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    lines = []
    for slide_index, slide in enumerate(prs.slides, start=1):
        lines.append(f"[Slide {slide_index}]")
        for shape in slide.shapes:
            if hasattr(shape, "text") and str(shape.text or "").strip():
                lines.append(str(shape.text).strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        lines.append(" | ".join(cells))
    return "\n".join(lines)
```

Add routing:

```python
        elif extension == ".pptx":
            text = _read_pptx(file_path)
        elif extension in LEGACY_OFFICE_EXTENSIONS:
            converted = convert_with_libreoffice(
                file_path,
                output_dir=config.TRADITIONAL_RAG_STORAGE_ROOT / "office_cache" / file_path.stem,
                libreoffice_path=config.LIBREOFFICE_PATH,
            )
            loaded = load_document_text(converted)
            text = loaded.text
            metadata_extra.update({"converted_from": extension, "converted_path": str(converted)})
```

- [ ] **Step 4: Run document loader tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rag-anything-api\rag_engines\traditional\document_parsers\office_converter.py rag-anything-api\rag_engines\traditional\document_loader.py rag-anything-api\tests\test_traditional_document_loader.py
git commit -m "feat: support pptx and legacy office conversion"
```

---

### Task 4: Audio and Video Transcription

**Files:**
- Create: `rag-anything-api/rag_engines/traditional/document_parsers/media_parser.py`
- Modify: `rag-anything-api/rag_engines/traditional/document_loader.py`
- Test: `rag-anything-api/tests/test_traditional_media_parser.py`
- Test: `rag-anything-api/tests/test_traditional_document_loader.py`

- [ ] **Step 1: Write failing media parser tests**

Add `rag-anything-api/tests/test_traditional_media_parser.py`:

```python
from pathlib import Path

import pytest

from rag_engines.traditional.document_parsers.common import ParserUnavailable
from rag_engines.traditional.document_parsers.media_parser import transcribe_audio, extract_audio_from_video


def test_transcribe_audio_requires_whisper(tmp_path: Path):
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"fake audio")

    with pytest.raises(ParserUnavailable) as exc:
        transcribe_audio(audio, whisper_available=False)

    assert "Whisper" in str(exc.value)


def test_extract_audio_from_video_requires_ffmpeg(tmp_path: Path):
    video = tmp_path / "sample.mp4"
    video.write_bytes(b"fake video")

    with pytest.raises(ParserUnavailable) as exc:
        extract_audio_from_video(video, output_dir=tmp_path / "cache", ffmpeg_path="")

    assert "ffmpeg" in str(exc.value)
```

Extend document loader tests:

```python
def test_audio_requires_whisper_when_missing(tmp_path: Path, monkeypatch):
    source = tmp_path / "call.mp3"
    source.write_bytes(b"fake audio")
    monkeypatch.setattr("rag_engines.traditional.document_loader.config.WHISPER_AVAILABLE", False)

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(source)

    assert "Whisper" in str(exc.value)


def test_video_requires_ffmpeg_when_missing(tmp_path: Path, monkeypatch):
    source = tmp_path / "demo.mp4"
    source.write_bytes(b"fake video")
    monkeypatch.setattr("rag_engines.traditional.document_loader.config.FFMPEG_PATH", "")

    with pytest.raises(UnsupportedDocumentType) as exc:
        load_document_text(source)

    assert "ffmpeg" in str(exc.value)
```

- [ ] **Step 2: Run media tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_media_parser.py rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: FAIL because `media_parser.py` does not exist.

- [ ] **Step 3: Implement media parser**

Create `rag-anything-api/rag_engines/traditional/document_parsers/media_parser.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import DocumentParsingError, ParsedDocument, ParserUnavailable


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}


def transcribe_audio(path: str | Path, whisper_available: bool = True) -> ParsedDocument:
    source = Path(path)
    if not whisper_available:
        raise ParserUnavailable("当前环境未检测到 Whisper，无法转写音频。请安装 openai-whisper 或上传文本资料。")
    try:
        import whisper
    except ImportError as exc:
        raise ParserUnavailable("当前环境未检测到 Whisper，无法转写音频。请安装 openai-whisper 或上传文本资料。") from exc

    model = whisper.load_model("base")
    result = model.transcribe(str(source), language="zh")
    text = str(result.get("text") or "").strip()
    if not text:
        raise DocumentParsingError(f"Whisper 未转写出可索引文本: {source.name}")
    return ParsedDocument(text=text, metadata={"parser": "whisper", "media_type": "audio"})


def extract_audio_from_video(path: str | Path, output_dir: str | Path, ffmpeg_path: str) -> Path:
    source = Path(path)
    if not ffmpeg_path:
        raise ParserUnavailable("当前环境未检测到 ffmpeg，无法从视频提取音轨。请安装 ffmpeg 或上传音频/文本资料。")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    audio_path = target_dir / f"{source.stem}.wav"
    command = [ffmpeg_path, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise DocumentParsingError(f"ffmpeg 提取音轨失败: {message or source.name}")
    return audio_path


def transcribe_video(path: str | Path, output_dir: str | Path, ffmpeg_path: str, whisper_available: bool = True) -> ParsedDocument:
    audio_path = extract_audio_from_video(path, output_dir=output_dir, ffmpeg_path=ffmpeg_path)
    parsed = transcribe_audio(audio_path, whisper_available=whisper_available)
    parsed.metadata.update({"media_type": "video", "audio_path": str(audio_path)})
    return parsed
```

Route media files in `document_loader.py`:

```python
from .document_parsers.media_parser import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, transcribe_audio, transcribe_video
```

Add branches:

```python
        elif extension in AUDIO_EXTENSIONS:
            parsed = transcribe_audio(file_path, whisper_available=config.WHISPER_AVAILABLE)
            text = parsed.text
            metadata_extra.update(parsed.metadata)
        elif extension in VIDEO_EXTENSIONS:
            parsed = transcribe_video(
                file_path,
                output_dir=config.TRADITIONAL_RAG_STORAGE_ROOT / "media_cache" / file_path.stem,
                ffmpeg_path=config.FFMPEG_PATH,
                whisper_available=config.WHISPER_AVAILABLE,
            )
            text = parsed.text
            metadata_extra.update(parsed.metadata)
```

- [ ] **Step 4: Run media tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_media_parser.py rag-anything-api\tests\test_traditional_document_loader.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add rag-anything-api\rag_engines\traditional\document_parsers\media_parser.py rag-anything-api\rag_engines\traditional\document_loader.py rag-anything-api\tests\test_traditional_media_parser.py rag-anything-api\tests\test_traditional_document_loader.py
git commit -m "feat: add audio and video transcription parsers"
```

---

### Task 5: Multi-Stage Retrieval

**Files:**
- Create: `rag-anything-api/rag_engines/traditional/retrieval.py`
- Modify: `rag-anything-api/rag_engines/traditional/engine.py`
- Modify: `rag-anything-api/rag_engines/traditional/vector_store.py`
- Modify: `rag-anything-api/rag_engines/factory.py`
- Test: `rag-anything-api/tests/test_traditional_retrieval.py`
- Test: `rag-anything-api/tests/test_traditional_engine.py`

- [ ] **Step 1: Write failing retrieval tests**

Add `rag-anything-api/tests/test_traditional_retrieval.py`:

```python
from rag_engines.traditional.retrieval import (
    RetrievalConfig,
    build_rewrite_queries,
    dedupe_candidates,
    filter_candidates,
    assign_source_ids,
)


def test_build_rewrite_queries_includes_original_and_history_terms():
    queries = build_rewrite_queries(
        "办理需要什么资料？",
        history=[{"q": "商务彩铃怎么开通？", "a": "需要企业信息。"}],
        enabled=True,
        max_queries=3,
    )

    assert queries[0] == "办理需要什么资料？"
    assert any("商务彩铃" in item for item in queries)
    assert len(queries) <= 3


def test_dedupe_candidates_prefers_highest_score():
    candidates = [
        {"text": "A", "score": 0.3, "metadata": {"chunk_index": 1}, "document_sha256": "doc"},
        {"text": "A", "score": 0.8, "metadata": {"chunk_index": 1}, "document_sha256": "doc"},
    ]

    deduped = dedupe_candidates(candidates)

    assert len(deduped) == 1
    assert deduped[0]["score"] == 0.8


def test_filter_candidates_uses_min_score():
    config = RetrievalConfig(min_score=0.5, candidates=20, final_contexts=8, rewrite_enabled=True, max_rewrite_queries=3)

    result = filter_candidates(
        [{"text": "low", "score": 0.1}, {"text": "high", "score": 0.7}],
        config,
    )

    assert [item["text"] for item in result] == ["high"]


def test_assign_source_ids_is_stable():
    result = assign_source_ids([{"text": "A", "metadata": {}}, {"text": "B", "metadata": {}}])

    assert result[0]["source_id"] == "来源 1"
    assert result[1]["source_id"] == "来源 2"
```

- [ ] **Step 2: Run retrieval tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_retrieval.py -q
```

Expected: FAIL because `retrieval.py` does not exist.

- [ ] **Step 3: Implement retrieval helpers**

Create `rag-anything-api/rag_engines/traditional/retrieval.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalConfig:
    min_score: float
    candidates: int
    final_contexts: int
    rewrite_enabled: bool
    max_rewrite_queries: int


def build_rewrite_queries(query: str, history: list[dict[str, str]] | None, enabled: bool, max_queries: int) -> list[str]:
    base = str(query or "").strip()
    if not base:
        return []
    if not enabled:
        return [base]
    queries = [base]
    for turn in reversed(history or []):
        previous = str(turn.get("q") or "").strip()
        if previous and previous not in base:
            queries.append(f"{previous}；{base}")
        if len(queries) >= max(1, int(max_queries)):
            break
    return queries[: max(1, int(max_queries))]


def _candidate_key(item: dict[str, Any]) -> tuple[str, str]:
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    document_sha = str(item.get("document_sha256") or meta.get("document_sha256") or "")
    chunk_index = str(meta.get("chunk_index") or "")
    if document_sha and chunk_index:
        return ("chunk", f"{document_sha}:{chunk_index}")
    text_hash = hashlib.sha1(str(item.get("text") or "").encode("utf-8")).hexdigest()
    return ("text", text_hash)


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for item in candidates:
        key = _candidate_key(item)
        current = best.get(key)
        if current is None or float(item.get("score") or 0) > float(current.get("score") or 0):
            best[key] = dict(item)
    return sorted(best.values(), key=lambda item: float(item.get("score") or 0), reverse=True)


def filter_candidates(candidates: list[dict[str, Any]], config: RetrievalConfig) -> list[dict[str, Any]]:
    return [item for item in candidates if float(item.get("score") or 0) >= float(config.min_score)]


def apply_rerank_order(candidates: list[dict[str, Any]], reranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not reranked:
        return candidates
    ordered = []
    for item in reranked:
        index = int(item.get("index", 0))
        if 0 <= index < len(candidates):
            copy = dict(candidates[index])
            copy["rerank_score"] = item.get("relevance_score")
            ordered.append(copy)
    return ordered or candidates


def assign_source_ids(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for index, item in enumerate(candidates, start=1):
        copy = dict(item)
        copy["source_id"] = f"来源 {index}"
        enriched.append(copy)
    return enriched
```

- [ ] **Step 4: Update vector store to return stable chunk metadata**

In `vector_store.py`, add row id and chunk index to results:

```python
"id": int(row["id"]),
"chunk_index": int(row["chunk_index"]),
"metadata": {**json.loads(row["metadata_json"]), "document_sha256": row["document_sha256"], "chunk_index": int(row["chunk_index"])},
```

- [ ] **Step 5: Update traditional engine query_context to use multi-stage retrieval**

In `engine.py`, import `RetrievalConfig` helpers and accept `retrieval_config` in `__init__`:

```python
from .retrieval import (
    RetrievalConfig,
    apply_rerank_order,
    assign_source_ids,
    build_rewrite_queries,
    dedupe_candidates,
    filter_candidates,
)
```

Add constructor parameter:

```python
        retrieval_config: RetrievalConfig | None = None,
```

Store default:

```python
        self.retrieval_config = retrieval_config or RetrievalConfig(
            min_score=0.2,
            candidates=20,
            final_contexts=8,
            rewrite_enabled=True,
            max_rewrite_queries=3,
        )
```

Add method:

```python
    async def retrieve_contexts(self, database_id: str, query: str, history: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        config = self.retrieval_config
        queries = build_rewrite_queries(query, history=history, enabled=config.rewrite_enabled, max_queries=config.max_rewrite_queries)
        all_candidates = []
        for item_query in queries:
            embeddings = await self.embedding_client.embed([item_query])
            all_candidates.extend(self._store(database_id).search(database_id, embeddings[0], top_k=config.candidates))
        candidates = filter_candidates(dedupe_candidates(all_candidates), config)
        if self.rerank_client and candidates:
            docs = [item["text"] for item in candidates]
            reranked = await self.rerank_client.rerank(query, docs, top_n=min(len(docs), config.final_contexts))
            candidates = apply_rerank_order(candidates, reranked)
        return assign_source_ids(candidates[: config.final_contexts])
```

Update `query_context` to call `retrieve_contexts` and trim text as it already does.

- [ ] **Step 6: Wire retrieval config in factory**

In `rag_engines/factory.py`, pass:

```python
from rag_engines.traditional.retrieval import RetrievalConfig
```

Inside `create_traditional_engine()`:

```python
        retrieval_config=RetrievalConfig(
            min_score=config.KB_MIN_SCORE,
            candidates=config.KB_RETRIEVAL_CANDIDATES,
            final_contexts=config.KB_FINAL_CONTEXTS,
            rewrite_enabled=config.KB_QUERY_REWRITE_ENABLED,
            max_rewrite_queries=config.KB_MAX_REWRITE_QUERIES,
        ),
```

- [ ] **Step 7: Run retrieval and engine tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_retrieval.py rag-anything-api\tests\test_traditional_engine.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add rag-anything-api\rag_engines\traditional\retrieval.py rag-anything-api\rag_engines\traditional\engine.py rag-anything-api\rag_engines\traditional\vector_store.py rag-anything-api\rag_engines\factory.py rag-anything-api\tests\test_traditional_retrieval.py rag-anything-api\tests\test_traditional_engine.py
git commit -m "feat: add multi-stage traditional rag retrieval"
```

---

### Task 6: Source-Cited Knowledge Answers

**Files:**
- Modify: `rag-anything-api/kb_answer.py`
- Modify: `rag-anything-api/app.py`
- Test: `rag-anything-api/tests/test_kb_answer.py`

- [ ] **Step 1: Write failing answer prompt tests**

Add `rag-anything-api/tests/test_kb_answer.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_answer import build_kb_answer_prompt, extract_source_summaries


def test_source_summaries_include_source_ids_and_chunk_metadata():
    contexts = [
        {
            "source_id": "来源 1",
            "text": "办理需要营业执照。",
            "score": 0.73,
            "rerank_score": 0.91,
            "document_sha256": "abc",
            "metadata": {"source": "guide.pdf", "chunk_index": 2},
        }
    ]

    sources = extract_source_summaries(contexts)

    assert sources[0]["source_id"] == "来源 1"
    assert sources[0]["file_name"] == "guide.pdf"
    assert sources[0]["chunk_index"] == 2
    assert sources[0]["document_sha256"] == "abc"
    assert sources[0]["rerank_score"] == 0.91


def test_answer_prompt_requires_source_citations():
    prompt = build_kb_answer_prompt(
        "怎么办理？",
        [{"source_id": "来源 1", "text": "提交营业执照。", "metadata": {"source": "guide.pdf"}}],
        history=[],
    )

    assert "只能基于【知识库资料】回答" in prompt
    assert "[来源 1]" in prompt
    assert "关键句后标注来源编号" in prompt
```

- [ ] **Step 2: Run answer tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_kb_answer.py -q
```

Expected: FAIL because source summaries do not include all enriched fields and prompt lacks citation wording.

- [ ] **Step 3: Enrich source summaries**

In `kb_answer.py`, update `extract_source_summaries`:

```python
        sources.append(
            {
                "source_id": str(ctx.get("source_id") or f"来源 {len(sources) + 1}"),
                "file_name": file_name,
                "snippet": snippet,
                "score": float(ctx.get("score") or 0),
                "rerank_score": ctx.get("rerank_score"),
                "chunk_index": meta.get("chunk_index"),
                "document_sha256": ctx.get("document_sha256") or meta.get("document_sha256"),
                "engine": str(meta.get("engine") or "").strip(),
            }
        )
```

- [ ] **Step 4: Update answer prompt**

In `build_kb_answer_prompt`, add source citation rules:

```python
        "回答必须先给直接结论，再列出关键依据。",
        "使用资料中的事实时，在关键句后标注来源编号，例如：[来源 1]。",
        "如果资料只覆盖部分问题，说明已找到的信息和缺少的信息。",
```

When listing contexts, use `source_id`:

```python
            source_id = str(ctx.get("source_id") or f"来源{index}")
            lines.append(f"[{source_id}｜文件：{source}]")
```

- [ ] **Step 5: Pass history into traditional retrieval from `/kb/chat`**

In `app.py`, change:

```python
        context_result = await engine.query_context(
            db_id,
            request.query,
            mode=config.CONTEXT_QUERY_MODE,
            max_chars=config.CONTEXT_MAX_CHARS,
        )
```

to:

```python
        if hasattr(engine, "retrieve_contexts"):
            contexts = await engine.retrieve_contexts(db_id, request.query, history=request.history or [])
            context_result = {"query": request.query, "database": db_id, "contexts": contexts}
        else:
            context_result = await engine.query_context(
                db_id,
                request.query,
                mode=config.CONTEXT_QUERY_MODE,
                max_chars=config.CONTEXT_MAX_CHARS,
            )
```

- [ ] **Step 6: Run answer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_kb_answer.py rag-anything-api\tests\test_traditional_engine.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add rag-anything-api\kb_answer.py rag-anything-api\app.py rag-anything-api\tests\test_kb_answer.py
git commit -m "feat: cite knowledge answer sources"
```

---

### Task 7: Force Traditional RAG in User-Facing Database Flow

**Files:**
- Modify: `rag-anything-api/app.py`
- Modify: `rag-anything-api/database_registry.py`
- Test: `rag-anything-api/tests/test_database_management_api.py`

- [ ] **Step 1: Write failing API tests**

In `rag-anything-api/tests/test_database_management_api.py`, add or update tests:

```python
def test_register_database_forces_traditional_engine(client):
    response = client.post(
        "/db/register",
        json={"id": "forced_traditional", "name": "Forced Traditional", "engine": "raganything"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["database"]["engine"] == "traditional"


def test_update_database_rejects_raganything_switch(client):
    client.post("/db/register", json={"id": "no_switch", "name": "No Switch"})

    response = client.put("/db/no_switch", json={"engine": "raganything"})

    assert response.status_code == 400
    assert "RAG-Anything" in response.json()["detail"]
```

Adapt fixture names to the existing test file if it uses a different client fixture.

- [ ] **Step 2: Run management tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_management_api.py -q
```

Expected: FAIL because `raganything` is currently accepted.

- [ ] **Step 3: Force traditional on register**

In `app.py` `register_database`, replace `engine=_normalize_engine_name(request.engine)` with:

```python
            engine="traditional",
```

- [ ] **Step 4: Reject user-facing engine switch to RAG-Anything**

In `app.py` `update_database`, before calling registry update:

```python
        requested_engine = _normalize_engine_name(request.engine)
        if requested_engine == "raganything":
            raise HTTPException(status_code=400, detail="前端知识库已统一使用传统 RAG，不再支持切换到 RAG-Anything。")
```

Pass `engine=requested_engine` to the registry update.

- [ ] **Step 5: Run management tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_management_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add rag-anything-api\app.py rag-anything-api\tests\test_database_management_api.py
git commit -m "feat: force user databases to traditional rag"
```

---

### Task 8: Frontend Knowledge UI and Source Rendering

**Files:**
- Modify: `ai-tutor-system/static/js/knowledge.js`
- Modify: `ai-tutor-system/static/js/knowledge-chat.js`

- [ ] **Step 1: Remove engine picker and engine badges in knowledge management**

In `knowledge.js`, replace the RAG engine form group with no markup. Remove the `renderEngineBadge` usage from database rows, file rows, upload logs, and upload hints.

Set upload accepted extensions:

```javascript
const accept = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.webp,.mp3,.wav,.flac,.aac,.ogg,.m4a,.mp4,.avi,.mkv,.mov,.webm';
const hint = '支持格式：PDF、Word(.doc/.docx)、Excel(.xls/.xlsx)、PPT(.ppt/.pptx)、TXT、Markdown、CSV、图片(.png/.jpg/.jpeg/.bmp/.tiff/.webp)、音频、视频';
```

In `createKnowledgeBase`, remove `engineInput`, set payload:

```javascript
{ id, name, description }
```

In upload status messages, use:

```javascript
return message.replace(/正在\s*RAG-Anything\s*解析[:：]?|正在\s*传统 RAG\s*分块索引[:：]?/, '正在解析并索引:');
```

- [ ] **Step 2: Render source IDs in knowledge chat**

In `knowledge-chat.js`, map sources with `sourceId`:

```javascript
return {
    sourceId: String((item && item.source_id) || '').trim() || ('来源 ' + (index + 1)),
    fileName: String((item && item.file_name) || '').trim() || '知识库资料',
    snippet: String((item && item.snippet) || '').trim() || '已命中该来源，未返回可展示片段。',
    score: typeof item.score === 'number' ? item.score : 0,
    rerankScore: typeof item.rerank_score === 'number' ? item.rerank_score : 0,
    chunkIndex: item && item.chunk_index,
    engine: String((item && item.engine) || '').trim(),
};
```

Update source item heading:

```javascript
'<div class="kbchat-source-file"><span class="kbchat-source-number">' + esc(item.sourceId) + '</span>' + esc(item.fileName || '知识库资料') + '</div>'
```

Show rerank score when present:

```javascript
var rerankText = item.rerankScore ? '<span class="kbchat-source-score">重排 ' + esc((Math.round(item.rerankScore * 100) / 100).toFixed(2)) + '</span>' : '';
```

- [ ] **Step 3: Run JavaScript syntax checks**

Run:

```powershell
node --check ai-tutor-system\static\js\knowledge.js
node --check ai-tutor-system\static\js\knowledge-chat.js
```

Expected: both commands complete without syntax errors.

- [ ] **Step 4: Commit**

```powershell
git add ai-tutor-system\static\js\knowledge.js ai-tutor-system\static\js\knowledge-chat.js
git commit -m "feat: simplify knowledge ui for traditional rag"
```

---

### Task 9: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `SETUP.md`
- Modify: `rag_database_guide.md`
- Modify: `使用说明.md`

- [ ] **Step 1: Update README knowledge-base section**

Change the public description to state:

```markdown
传统 RAG 是用户可见的唯一知识库引擎。系统使用 MinerU/LibreOffice/Whisper/ffmpeg 等解析工具把 PDF、扫描件、图片、Office 文档、音频和视频转换为可检索文本，再使用 SQLite 向量索引、embedding 和 rerank 完成问答。
```

List supported formats:

```markdown
- 文档：.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx, .txt, .md, .csv
- 图片：.png, .jpg, .jpeg, .bmp, .tiff, .webp
- 音频：.mp3, .wav, .flac, .aac, .ogg, .m4a
- 视频：.mp4, .avi, .mkv, .mov, .webm
```

- [ ] **Step 2: Update setup dependency section**

In `SETUP.md`, add:

```markdown
### 知识库解析依赖

- MinerU：用于扫描版 PDF、复杂版面 PDF 和图片 OCR。
- LibreOffice：用于 .doc/.xls/.ppt 老 Office 格式转换。
- ffmpeg：用于视频音轨提取。
- openai-whisper：用于音频和视频转写。
```

- [ ] **Step 3: Update RAG guide and usage docs**

In `rag_database_guide.md` and `使用说明.md`, remove user-facing instructions for switching to RAG-Anything. Explain that RAG-Anything code remains internally for compatibility, but new user-created knowledge bases use traditional RAG.

- [ ] **Step 4: Run targeted backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_traditional_dependencies.py rag-anything-api\tests\test_traditional_mineru_parser.py rag-anything-api\tests\test_traditional_media_parser.py rag-anything-api\tests\test_traditional_document_loader.py rag-anything-api\tests\test_traditional_retrieval.py rag-anything-api\tests\test_traditional_engine.py rag-anything-api\tests\test_kb_answer.py rag-anything-api\tests\test_database_management_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Run full test and compile checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests -q
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests -q
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api
node --check ai-tutor-system\static\js\knowledge.js
node --check ai-tutor-system\static\js\knowledge-chat.js
```

Expected: all commands pass with no syntax errors.

- [ ] **Step 6: Commit docs and verification fixes**

```powershell
git add README.md SETUP.md rag_database_guide.md 使用说明.md
git commit -m "docs: update knowledge base rag workflow"
```

---

## Self-Review

Spec coverage:

- Frontend hides RAG-Anything: Task 8.
- New DBs forced to traditional RAG: Task 7.
- PDF OCR and image OCR via MinerU: Task 2.
- PPT/PPTX, DOC/DOCX, XLS/XLSX: Task 3 and existing loaders.
- Audio/video transcription: Task 4.
- Multi-query retrieval, dedupe, threshold, rerank, source IDs: Task 5.
- Source-cited answer prompt and enriched sources: Task 6.
- Dependency status and clear dependency errors: Task 1, Task 2, Task 3, Task 4.
- Docs updates: Task 9.

Placeholder scan:

- No placeholder task text is required for execution.
- Each implementation task has failing tests, expected failure, code-level changes, verification, and commit command.

Type consistency:

- Parser exceptions are `ParserUnavailable` and `DocumentParsingError`.
- Parser outputs use `ParsedDocument(text, metadata)`.
- Retrieval config is `RetrievalConfig(min_score, candidates, final_contexts, rewrite_enabled, max_rewrite_queries)`.
- Source metadata uses `source_id`, `file_name`, `snippet`, `score`, `rerank_score`, `chunk_index`, and `document_sha256`.
