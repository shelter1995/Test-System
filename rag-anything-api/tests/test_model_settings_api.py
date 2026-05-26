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


def test_put_model_settings_rebuilds_traditional_engine(client, monkeypatch):
    created = object()
    monkeypatch.setattr(rag_api, "create_traditional_engine", lambda: created)

    response = client.put(
        "/settings/models",
        json={
            "embedding": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "custom-embed",
            }
        },
    )

    assert response.status_code == 200
    assert rag_api.traditional_service is created


def test_root_describes_traditional_rag_and_runtime_models(client):
    client.put(
        "/settings/models",
        json={
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "qwen-local",
                "timeout": 45,
            },
            "embedding": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "bge-local",
                "dimension": 1024,
            },
            "rerank": {
                "enabled": True,
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "rerank-local",
            },
        },
    )

    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "传统 RAG 知识库服务正在运行"
    assert data["engine"] == "Traditional RAG + Vector Search + Rerank"
    assert data["llm"] == "openai-compatible qwen-local"
    assert data["embedding"] == "openai-compatible bge-local"
    assert data["query"]["rerank"] == "enabled"
    assert "RAGAnything" not in str(data)
    assert "MiniMax-M2.5" not in str(data)


def test_status_reports_runtime_model_settings(client):
    client.put(
        "/settings/models",
        json={
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:11434/v1", "model": "qwen-local"},
            "embedding": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "bge-local",
                "dimension": 768,
                "timeout": 12,
            },
            "rerank": {
                "enabled": False,
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "rerank-local",
            },
        },
    )

    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "传统 RAG 知识库服务"
    assert data["engine_stack"] == "Traditional RAG + Vector Search + Rerank"
    assert data["llm"]["provider"] == "openai-compatible"
    assert data["llm"]["model"] == "qwen-local"
    assert "fallback" not in data["llm"]
    assert data["embedding"]["provider"] == "openai-compatible"
    assert data["embedding"]["model"] == "bge-local"
    assert data["embedding"]["dimension"] == 768
    assert data["rerank"]["enabled"] is False
    assert data["rerank"]["model"] == "rerank-local"
    assert "RAGAnything" not in str(data)


def test_kb_chat_uses_runtime_llm_settings(client, monkeypatch):
    captured = {}

    class FakeRegistry:
        def get_database(self, db_id):
            return {"id": db_id, "engine": "traditional", "documents": []}

    class FakeRagService:
        registry = FakeRegistry()

        async def generate_answer(self, prompt):
            raise AssertionError("kb_chat should use runtime model settings, not legacy service LLM")

    class FakeTraditionalEngine:
        async def query_context(self, database_id, query, mode="naive", max_chars=3000):
            return {
                "query": query,
                "database": database_id,
                "contexts": [
                    {
                        "text": "产品价格为 10 元/月。",
                        "metadata": {"source": "price.md", "database": database_id},
                        "score": 0.9,
                    }
                ],
                "total_found": 1,
                "fallback": "",
            }

    class FakeClient:
        def __init__(self, endpoint):
            captured["endpoint"] = endpoint

        async def chat(self, system_prompt, user_prompt):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return "基于知识库，产品价格为 10 元/月。"

    monkeypatch.setattr(rag_api, "OpenAICompatibleClient", FakeClient)
    client.put(
        "/settings/models",
        json={"llm": {"provider": "openai-compatible", "base_url": "http://localhost:11434/v1", "model": "qwen-local"}},
    )
    monkeypatch.setattr(rag_api, "rag_service", FakeRagService())
    monkeypatch.setattr(rag_api, "traditional_service", FakeTraditionalEngine())

    response = client.post("/kb/chat", json={"database": "sales", "query": "价格是多少"})

    assert response.status_code == 200
    assert response.json()["answer"] == "基于知识库，产品价格为 10 元/月。"
    assert captured["endpoint"].provider == "openai-compatible"
    assert captured["endpoint"].base_url == "http://localhost:11434/v1"
    assert captured["endpoint"].model == "qwen-local"
    assert captured["system_prompt"] == "你是严谨的中文知识库问答助手。"


def test_llm_chat_proxy_uses_runtime_model_settings(client, monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, endpoint):
            captured["endpoint"] = endpoint

        async def chat(self, system_prompt, user_prompt, temperature=0.2, max_tokens=None):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            captured["temperature"] = temperature
            captured["max_tokens"] = max_tokens
            return "统一模型回复"

    monkeypatch.setattr(rag_api, "OpenAICompatibleClient", FakeClient)
    client.put(
        "/settings/models",
        json={"llm": {"provider": "openai-compatible", "base_url": "http://localhost:11434/v1", "model": "deepseek-chat"}},
    )

    response = client.post(
        "/llm/chat",
        json={
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "用户问题"},
            ],
            "temperature": 0.4,
            "max_tokens": 2000,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["content"] == "统一模型回复"
    assert data["model"] == "deepseek-chat"
    assert captured["endpoint"].model == "deepseek-chat"
    assert captured["system_prompt"] == "系统提示"
    assert captured["user_prompt"] == "用户问题"
    assert captured["temperature"] == 0.4
    assert captured["max_tokens"] == 2000
