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


def test_providers_include_model_catalog(tmp_path: Path):
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")

    providers = store.providers()

    assert "MiniMax-M2.7" in providers["models"]["llm"]["minimax"]
    assert "BAAI/bge-m3" in providers["models"]["embedding"]["siliconflow"]
    assert "BAAI/bge-reranker-v2-m3" in providers["models"]["rerank"]["siliconflow"]


def test_save_ignores_runtime_test_target(tmp_path: Path):
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")

    store.save({"target": "embedding", "embedding": {"model": "BAAI/bge-m3"}})

    assert "target" not in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_runtime_override_blank_api_key_keeps_saved_secret(tmp_path: Path):
    store = ModelSettingsStore(tmp_path / "settings.json", tmp_path / "local.json")
    store.save(
        {
            "persist_api_key": True,
            "embedding": {
                "provider": "siliconflow",
                "base_url": "https://api.siliconflow.cn/v1",
                "model": "BAAI/bge-m3",
                "api_key": "saved-key",
            },
        }
    )

    runtime = store.runtime(
        {
            "target": "embedding",
            "embedding": {
                "provider": "siliconflow",
                "base_url": "https://api.siliconflow.cn/v1",
                "model": "Pro/BAAI/bge-m3",
                "api_key": "",
            },
        }
    )

    assert runtime["embedding"]["api_key"] == "saved-key"
    assert runtime["embedding"]["model"] == "Pro/BAAI/bge-m3"
