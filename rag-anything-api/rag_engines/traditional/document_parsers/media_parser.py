from __future__ import annotations

import os
import subprocess
from pathlib import Path

import numpy as np

from .common import DocumentParsingError, ParserUnavailable

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v"}


def _decode_audio_to_pcm_array(path: Path, ffmpeg_path: str) -> np.ndarray:
    """Decode ``path`` to a 16kHz mono float32 numpy array using ``ffmpeg_path``.

    Bypasses ``whisper.audio.load_audio`` so we never depend on a ``ffmpeg``
    binary named exactly ``ffmpeg`` being on PATH (imageio-ffmpeg ships a
    versioned filename that Windows cannot find by that name).
    """
    binary = ffmpeg_path.strip()
    if not binary:
        raise ParserUnavailable("ffmpeg binary not found.")

    cmd = [
        binary,
        "-nostdin",
        "-threads",
        "0",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-ac",
        "1",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise ParserUnavailable(f"ffmpeg binary not found: {binary}") from exc
    except OSError as exc:
        raise ParserUnavailable(f"ffmpeg binary not found: {binary}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore").strip()
        message = stderr or "ffmpeg decode failed."
        raise DocumentParsingError(f"ffmpeg decode failed: {message}") from exc

    if not result.stdout:
        raise DocumentParsingError("ffmpeg decode returned no audio data.")

    pcm = np.frombuffer(result.stdout, dtype=np.int16).flatten()
    return pcm.astype(np.float32) / 32768.0


def transcribe_audio(path: str | Path, whisper_available: bool, ffmpeg_path: str | Path | None = None) -> str:
    source_path = Path(path)
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(str(source_path))

    binary = str(ffmpeg_path or "").strip()
    if not binary:
        raise ParserUnavailable("ffmpeg binary not found.")

    try:
        import whisper
    except ImportError as exc:
        message = "Whisper is not installed."
        if whisper_available:
            message = "Whisper was reported available but could not be imported."
        raise ParserUnavailable(message) from exc

    try:
        model_name = os.getenv("WHISPER_MODEL", "base")
        download_root = os.getenv("WHISPER_CACHE_DIR") or None
        model = whisper.load_model(model_name, download_root=download_root)
        audio = _decode_audio_to_pcm_array(source_path, ffmpeg_path=binary)
        result = model.transcribe(audio, fp16=False)
    except (ParserUnavailable, DocumentParsingError):
        raise
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
    return transcribe_audio(path=audio_path, whisper_available=whisper_available, ffmpeg_path=ffmpeg_path)
