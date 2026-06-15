from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from .common import DocumentParsingError, ParsedDocument, ParserUnavailable


MINERU_PARSE_TIMEOUT_SECONDS = 30 * 60
MINERU_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


def should_use_mineru_for_pdf(text: str, page_count: int) -> bool:
    content = text or ""
    compact = "".join(ch for ch in content if not ch.isspace())
    if not compact:
        return True

    pages = max(int(page_count or 1), 1)
    avg_chars_per_page = len(compact) / pages
    if avg_chars_per_page < 80:
        return True

    if _garbled_ratio(compact) >= 0.15:
        return True

    return False


def parse_with_mineru(
    path: str | Path,
    output_root: str | Path,
    mineru_path: str | Sequence[str],
) -> ParsedDocument:
    source_path = Path(path)
    out_root = Path(output_root)
    if isinstance(mineru_path, str):
        command_prefix = [mineru_path.strip()] if mineru_path.strip() else []
    else:
        command_prefix = [str(item).strip() for item in mineru_path if str(item).strip()]
    if not command_prefix:
        raise ParserUnavailable("MinerU CLI not configured.")
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    out_root.mkdir(parents=True, exist_ok=True)
    output_dir = out_root / f"{source_path.stem}_mineru"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        *command_prefix,
        "-p",
        str(source_path),
        "-o",
        str(output_dir),
    ]
    if source_path.suffix.lower() in MINERU_IMAGE_EXTENSIONS:
        cmd.extend(["-m", "ocr", "-b", "pipeline"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=MINERU_PARSE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ParserUnavailable(f"MinerU CLI not found: {' '.join(command_prefix)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DocumentParsingError(
            f"MinerU parsing timed out after {MINERU_PARSE_TIMEOUT_SECONDS} seconds."
        ) from exc
    except OSError as exc:
        raise DocumentParsingError(f"MinerU execution failed: {exc}") from exc

    if result.returncode != 0:
        error_message = (result.stderr or result.stdout or "").strip() or "unknown error"
        raise DocumentParsingError(f"MinerU parsing failed: {error_message}")

    parsed_text = _read_mineru_text_output(output_dir, result.stdout)
    if not parsed_text:
        raise DocumentParsingError("MinerU parsing succeeded but produced empty text output.")

    return ParsedDocument(
        text=parsed_text,
        metadata={
            "parser": "mineru",
            "output_dir": str(output_dir),
            "source_path": str(source_path),
        },
    )


def _read_mineru_text_output(output_dir: Path, stdout_text: str) -> str:
    for markdown_path in sorted(output_dir.rglob("*.md")):
        text = markdown_path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text
    return (stdout_text or "").strip()


def _garbled_ratio(text: str) -> float:
    if not text:
        return 1.0

    bad = 0
    for ch in text:
        if ch == "\ufffd":
            bad += 1
            continue
        code = ord(ch)
        if code < 32 and ch not in {"\n", "\r", "\t"}:
            bad += 1
    return bad / len(text)
