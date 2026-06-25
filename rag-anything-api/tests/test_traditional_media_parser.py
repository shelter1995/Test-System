from pathlib import Path
import builtins
import os
import subprocess
import sys
import types

import numpy as np
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
    ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    original_import = builtins.__import__

    def _missing_whisper(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    sys.modules.pop("whisper", None)
    builtins.__import__ = _missing_whisper

    try:
        with pytest.raises(ParserUnavailable) as exc:
            transcribe_audio(audio_path, whisper_available=False, ffmpeg_path=ffmpeg_path)
    finally:
        builtins.__import__ = original_import

    assert "Whisper" in str(exc.value)


def test_transcribe_audio_tries_import_even_when_dependency_probe_is_stale(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    captured: dict[str, object] = {}

    def _load_model(model_name, download_root=None):
        class _Model:
            def transcribe(self, audio, fp16=False):
                captured["audio_type"] = type(audio).__name__
                captured["audio"] = np.asarray(audio)
                return {"text": "运行中安装后可用的转写文本"}

        return _Model()

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=_load_model))
    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout=b"\x00\x00", stderr=b""),
    )

    text = transcribe_audio(audio_path, whisper_available=False, ffmpeg_path=ffmpeg_path)

    assert text == "运行中安装后可用的转写文本"
    assert captured["audio_type"] == "ndarray"
    assert captured["audio"].dtype == np.float32
    assert captured["audio"].shape == (1,)


def test_transcribe_audio_uses_configured_whisper_model_cache(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    pcm_int16 = np.array([0, 32767, -32768, 16384], dtype=np.int16)
    captured: dict[str, object] = {}

    def _load_model(model_name, download_root=None):
        captured["model_name"] = model_name
        captured["download_root"] = str(download_root)

        class _Model:
            def transcribe(self, audio, fp16=False):
                captured["audio_type"] = type(audio).__name__
                captured["audio_dtype"] = str(audio.dtype)
                captured["audio_shape"] = audio.shape
                captured["fp16"] = fp16
                return {"text": "转写文本"}

        return _Model()

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=_load_model))
    monkeypatch.setenv("WHISPER_MODEL", "small")
    monkeypatch.setenv("WHISPER_CACHE_DIR", str(tmp_path / "models" / "whisper"))
    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout=pcm_int16.tobytes(), stderr=b""),
    )

    text = transcribe_audio(audio_path, whisper_available=True, ffmpeg_path=ffmpeg_path)

    assert text == "转写文本"
    assert captured["model_name"] == "small"
    assert captured["download_root"] == str(tmp_path / "models" / "whisper")
    assert captured["audio_type"] == "ndarray"
    assert captured["audio_dtype"] == "float32"
    assert captured["audio_shape"] == (4,)
    assert captured["fp16"] is False


def test_transcribe_audio_raises_parser_unavailable_when_ffmpeg_path_empty(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")

    def _load_model(model_name, download_root=None):
        raise AssertionError("whisper.load_model should not be called when ffmpeg is missing")

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=_load_model))

    with pytest.raises(ParserUnavailable) as exc:
        transcribe_audio(audio_path, whisper_available=True, ffmpeg_path="")

    assert "ffmpeg" in str(exc.value).lower()


def test_transcribe_audio_raises_parsing_error_when_ffmpeg_subprocess_fails(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    ffmpeg_path = str(tmp_path / "ffmpeg.exe")

    def _load_model(model_name, download_root=None):
        class _Model:
            def transcribe(self, audio, fp16=False):
                raise AssertionError("whisper.transcribe should not be called when ffmpeg fails")

        return _Model()

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=_load_model))

    def _raise_called_process_error(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd=["ffmpeg"], stderr=b"decode failed")

    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        _raise_called_process_error,
    )

    with pytest.raises(DocumentParsingError) as exc:
        transcribe_audio(audio_path, whisper_available=True, ffmpeg_path=ffmpeg_path)

    assert "ffmpeg" in str(exc.value).lower()


def test_transcribe_audio_decodes_to_ndarray_and_passes_to_whisper(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")
    ffmpeg_path = str(tmp_path / "ffmpeg.exe")

    pcm_int16 = np.array([0, 32767, -32768, 16384], dtype=np.int16)
    pcm_bytes = pcm_int16.tobytes()
    captured: dict[str, object] = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["capture_output"] = kwargs.get("capture_output")
        captured["check"] = kwargs.get("check")
        return types.SimpleNamespace(returncode=0, stdout=pcm_bytes, stderr=b"")

    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        _fake_run,
    )

    def _load_model(model_name, download_root=None):
        class _Model:
            def transcribe(self, audio, fp16=False):
                captured["audio_type"] = type(audio).__name__
                captured["audio"] = np.asarray(audio)
                captured["fp16"] = fp16
                return {"text": "转写文本"}

        return _Model()

    monkeypatch.setitem(sys.modules, "whisper", types.SimpleNamespace(load_model=_load_model))

    text = transcribe_audio(audio_path, whisper_available=True, ffmpeg_path=ffmpeg_path)

    assert text == "转写文本"
    # ffmpeg must be invoked by its full path so it works on systems without ffmpeg on PATH
    assert captured["cmd"][0] == ffmpeg_path
    assert captured["capture_output"] is True
    assert captured["check"] is True
    # The audio passed to whisper is a float32 ndarray, not the file path
    assert captured["audio_type"] == "ndarray"
    audio = captured["audio"]
    assert audio.dtype == np.float32
    assert audio.shape == (4,)
    assert captured["fp16"] is False
    np.testing.assert_array_almost_equal(audio, pcm_int16.astype(np.float32) / 32768.0)


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


def test_extract_audio_from_video_uses_encoding_tolerant_subprocess(monkeypatch, tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    audio_path = tmp_path / "out" / "clip.wav"
    captured_kwargs = {}

    class _Result:
        returncode = 0
        stderr = ""
        stdout = ""

    def _fake_run(*args, **kwargs):
        captured_kwargs.update(kwargs)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio")
        return _Result()

    monkeypatch.setattr(
        "rag_engines.traditional.document_parsers.media_parser.subprocess.run",
        _fake_run,
    )

    result = extract_audio_from_video(video_path, output_dir=tmp_path / "out", ffmpeg_path="ffmpeg")

    assert result == audio_path
    assert captured_kwargs["encoding"] == "utf-8"
    assert captured_kwargs["errors"] == "ignore"


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

    def _fake_transcribe(path, whisper_available, ffmpeg_path=None):
        trace.append("transcribe")
        assert ffmpeg_path == "ffmpeg"
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
