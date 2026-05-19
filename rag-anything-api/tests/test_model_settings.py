from pathlib import Path

from model_settings import ModelSettingsStore


def test_default_settings_include_minimax_and_siliconflow(tmp_path: Path):
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")

    settings = store.load()

    assert settings["llm"]["provider"] == "minimax"
    assert settings["embedding"]["provider"] == "siliconflow"
    assert settings["rerank"]["provider"] == "siliconflow"


def test_save_non_secret_settings(tmp_path: Path):
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")

    saved = store.save(
        {
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:11434/v1", "model": "qwen"},
            "embedding": {"provider": "siliconflow", "model": "BAAI/bge-m3", "dimension": 1024},
            "rerank": {"provider": "siliconflow", "model": "BAAI/bge-reranker-v2-m3", "enabled": True},
        }
    )

    assert saved["llm"]["base_url"] == "http://localhost:11434/v1"
    assert "api_key" not in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_runtime_uses_siliconflow_key_for_rerank_when_specific_key_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.delenv("RERANK_API_KEY", raising=False)
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")

    settings = store.runtime()

    assert settings["rerank"]["api_key"] == "sf-key"
