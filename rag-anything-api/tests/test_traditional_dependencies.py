import importlib

from fastapi.testclient import TestClient

import app as rag_api


def test_detect_traditional_parser_dependencies_reports_all_keys(monkeypatch):
    from rag_engines.traditional import dependencies

    def fake_which(name: str):
        mapping = {
            "ffmpeg": "/tools/ffmpeg.exe",
            "soffice": "/tools/soffice.exe",
            "mineru": "/tools/mineru.exe",
        }
        return mapping.get(name)

    monkeypatch.setattr(dependencies.shutil, "which", fake_which)
    monkeypatch.setattr(dependencies, "_detect_whisper_cli_path", lambda: "/tools/whisper.exe")
    monkeypatch.delenv("LIBREOFFICE_PATH", raising=False)
    monkeypatch.delenv("MINERU_CLI_PATH", raising=False)

    result = dependencies.detect_traditional_parser_dependencies()

    assert set(result) == {"ffmpeg", "libreoffice", "mineru", "whisper"}
    assert result["ffmpeg"] == {"available": True, "path": "/tools/ffmpeg.exe"}
    assert result["libreoffice"] == {"available": True, "path": "/tools/soffice.exe"}
    assert result["mineru"] == {"available": True, "path": "/tools/mineru.exe"}
    assert result["whisper"] == {"available": True, "path": "/tools/whisper.exe"}


def test_config_exposes_traditional_parser_and_kb_query_settings(monkeypatch):
    monkeypatch.setenv("LIBREOFFICE_PATH", "C:/custom/soffice.exe")
    monkeypatch.setenv("MINERU_CLI_PATH", "C:/custom/mineru.exe")
    monkeypatch.setenv("KB_QUERY_REWRITE_ENABLED", "true")
    monkeypatch.setenv("KB_RETRIEVAL_CANDIDATES", "24")
    monkeypatch.setenv("KB_FINAL_CONTEXTS", "8")
    monkeypatch.setenv("KB_MIN_SCORE", "0.31")
    monkeypatch.setenv("KB_MAX_REWRITE_QUERIES", "3")

    import config

    config = importlib.reload(config)

    assert isinstance(config.TRADITIONAL_PARSER_DEPENDENCIES, dict)
    assert set(config.TRADITIONAL_PARSER_DEPENDENCIES) == {"ffmpeg", "libreoffice", "mineru", "whisper"}
    assert config.LIBREOFFICE_PATH == "C:/custom/soffice.exe"
    assert config.MINERU_CLI_PATH == "C:/custom/mineru.exe"
    assert config.KB_QUERY_REWRITE_ENABLED is True
    assert config.KB_RETRIEVAL_CANDIDATES == 24
    assert config.KB_FINAL_CONTEXTS == 8
    assert abs(config.KB_MIN_SCORE - 0.31) < 1e-9
    assert config.KB_MAX_REWRITE_QUERIES == 3


def test_status_includes_traditional_parser_dependencies(monkeypatch):
    payload = {
        "ffmpeg": {"available": True, "path": "/tools/ffmpeg.exe"},
        "libreoffice": {"available": False, "path": ""},
        "mineru": {"available": True, "path": "/tools/mineru.exe"},
        "whisper": {"available": False, "path": ""},
    }
    monkeypatch.setattr(rag_api.config, "TRADITIONAL_PARSER_DEPENDENCIES", payload)

    client = TestClient(rag_api.app)
    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["traditional_parser"] == payload
