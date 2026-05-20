from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

from .common import DocumentParsingError, ParserUnavailable

LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}

_TARGET_FORMATS = {
    ".doc": "docx",
    ".xls": "xlsx",
    ".ppt": "pptx",
}


def _resolve_libreoffice_executable(libreoffice_path: str) -> str:
    executable = (libreoffice_path or "").strip()
    if not executable:
        raise ParserUnavailable("LibreOffice executable is not configured.")

    direct_path = Path(executable)
    if direct_path.exists():
        return str(direct_path)

    resolved = which(executable)
    if resolved:
        return resolved

    raise ParserUnavailable(f"LibreOffice executable was not found: {executable}")


def convert_with_libreoffice(path: str | Path, output_dir: str | Path, libreoffice_path: str) -> Path:
    source_path = Path(path)
    extension = source_path.suffix.lower()
    if extension not in LEGACY_OFFICE_EXTENSIONS:
        raise ValueError(f"Unsupported legacy office extension: {extension}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    executable = _resolve_libreoffice_executable(libreoffice_path)
    target_format = _TARGET_FORMATS[extension]

    result = subprocess.run(
        [
            executable,
            "--headless",
            "--convert-to",
            target_format,
            "--outdir",
            str(out_dir),
            str(source_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "").strip()
        raise DocumentParsingError(f"LibreOffice conversion failed: {error_text or source_path.name}")

    converted_path = out_dir / f"{source_path.stem}.{target_format}"
    if not converted_path.exists():
        raise DocumentParsingError(
            f"LibreOffice conversion did not produce expected file: {converted_path.name}"
        )

    return converted_path
