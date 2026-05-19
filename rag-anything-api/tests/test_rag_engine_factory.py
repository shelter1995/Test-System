import json

from rag_engines import factory


def test_create_traditional_engine_uses_persisted_model_settings(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "model_settings.json").write_text(
        json.dumps(
            {
                "embedding": {
                    "provider": "openai-compatible",
                    "base_url": "http://localhost:11434/v1",
                    "model": "custom-embed",
                },
                "rerank": {
                    "enabled": True,
                    "provider": "openai-compatible",
                    "base_url": "http://localhost:11434/v1",
                    "model": "custom-rerank",
                    "api_key": "rerank-key",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(factory.config, "STORAGE_ROOT", storage)
    monkeypatch.setattr(factory.config, "TRADITIONAL_RAG_STORAGE_ROOT", storage / "traditional")

    engine = factory.create_traditional_engine()

    assert engine.embedding_client.endpoint.model == "custom-embed"
    assert engine.rerank_client.endpoint.model == "custom-rerank"


def test_create_traditional_engine_disables_rerank_without_api_key(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(factory.config, "STORAGE_ROOT", storage)
    monkeypatch.setattr(factory.config, "TRADITIONAL_RAG_STORAGE_ROOT", storage / "traditional")
    monkeypatch.delenv("RERANK_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    engine = factory.create_traditional_engine()

    assert engine.rerank_client is None
