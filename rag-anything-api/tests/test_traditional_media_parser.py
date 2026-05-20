from pathlib import Path

import pytest

from rag_engines.traditional.document_parsers import DocumentParsingError, ParserUnavailable
from rag_engines.traditional.document_parsers.media_parser import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    extract_audio_from_video,
    transcribe_audio,
    transcribe_video,
)


def test_extensions_are_defined():
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".wav" in AUDIO_EXTENSIONS
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mkv" in VIDEO_EXTENSIONS


def test_transcribe_audio_raises_when_whisper_unavailable(tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")

    with pytest.raises(ParserUnavailable) as exc:
        transcribe_audio(audio_path, whisper_available=False)

    assert "Whisper" in str(exc.value)


def test_extract_audio_from_video_raises_when_ffmpeg_missing(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    with pytest.raises(ParserUnavailable) as exc:
        extract_audio_from_video(video_path, output_dir=tmp_path / "out", ffmpeg_path="")

    assert "ffmpeg" in str(exc.value)


def test_extract_audio_from_video_raises_parsing_error_on_failure(monkeypatch, tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    class _Result:
        returncode = 1
        stderr = "decode failed"
        stdout = ""

    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )

    with pytest.raises(DocumentParsingError) as exc:
        extract_audio_from_video(video_path, output_dir=tmp_path / "out", ffmpeg_path="ffmpeg")

    assert "ffmpeg" in str(exc.value)


def test_transcribe_video_calls_extract_then_transcribe(monkeypatch, tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    audio_path = tmp_path / "out" / "clip.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")

    trace: list[str] = []

    def _fake_extract(path, output_dir, ffmpeg_path):
        trace.append("extract")
        return audio_path

    def _fake_transcribe(path, whisper_available):
        trace.append("transcribe")
        return "转写文本"

    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.extract_audio_from_video",
        _fake_extract,
    )
    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.transcribe_audio",
        _fake_transcribe,
    )

    text = transcribe_video(
        video_path,
        output_dir=tmp_path / "out",
        ffmpeg_path="ffmpeg",
        whisper_available=True,
    )

    assert text == "转写文本"
    assert trace == ["extract", "transcribe"]
