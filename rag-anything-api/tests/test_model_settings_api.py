import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as rag_api
from model_settings import ModelSettingsStore


@pytest.fixture()
def client(tmp_path):
    store = ModelSettingsStore(
        tmp_path / "model_settings.json",
        tmp_path / "model_settings.local.json",
    )
    rag_api.settings_store = store
    return TestClient(rag_api.app)


def test_get_model_settings(client):
    response = client.get("/settings/models")

    assert response.status_code == 200
    data = response.json()
    assert data["llm"]["provider"] == "minimax"
    assert data["embedding"]["provider"] == "siliconflow"


def test_get_settings_providers(client):
    response = client.get("/settings/providers")

    assert response.status_code == 200
    providers = response.json()["providers"]
    assert "minimax" in providers["llm"]
    assert "siliconflow" in providers["embedding"]
    assert "openai-compatible" in providers["llm"]


def test_put_model_settings_rejects_empty_model(client):
    response = client.put(
        "/settings/models",
        json={"llm": {"provider": "minimax", "model": ""}},
    )

    assert response.status_code == 400
