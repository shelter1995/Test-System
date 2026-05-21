from __future__ import annotations

import subprocess
from pathlib import Path

from .common import DocumentParsingError, ParserUnavailable

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"}


def transcribe_audio(path: str | Path, whisper_available: bool) -> str:
    source_path = Path(path)
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    if not whisper_available:
        raise ParserUnavailable("Whisper is not available.")

    try:
        import whisper
    except ImportError as exc:
        raise ParserUnavailable("Whisper is not installed.") from exc

    try:
        model = whisper.load_model("base")
        result = model.transcribe(str(source_path), fp16=False)
    except Exception as exc:  # pragma: no cover - runtime backend exceptions are environment specific
        raise DocumentParsingError(f"Whisper transcription failed: {exc}") from exc

    text = str(result.get("text", "")).strip()
    if not text:
        raise DocumentParsingError("Whisper transcription returned empty text.")
    return text


def extract_audio_from_video(path: str | Path, output_dir: str | Path, ffmpeg_path: str) -> Path:
    source_path = Path(path)
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    binary = str(ffmpeg_path or "").strip()
    if not binary:
        raise ParserUnavailable("ffmpeg is not available.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_path = out_dir / f"{source_path.stem}.wav"

    cmd = [
        binary,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
    except FileNotFoundError as exc:
        raise ParserUnavailable(f"ffmpeg binary not found: {binary}") from exc
    except OSError as exc:
        raise DocumentParsingError(f"ffmpeg execution failed: {exc}") from exc

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "unknown error"
        raise DocumentParsingError(f"ffmpeg extraction failed: {message}")

    if not audio_path.exists():
        raise DocumentParsingError("ffmpeg extraction succeeded but output audio is missing.")

    return audio_path


def transcribe_video(path: str | Path, output_dir: str | Path, ffmpeg_path: str, whisper_available: bool) -> str:
    audio_path = extract_audio_from_video(path=path, output_dir=output_dir, ffmpeg_path=ffmpeg_path)
    return transcribe_audio(path=audio_path, whisper_available=whisper_available)
