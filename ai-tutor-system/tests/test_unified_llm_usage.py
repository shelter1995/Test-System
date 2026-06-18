import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class FakeUnifiedClient:
    def __init__(self):
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "content": "统一模型回复"}

    def stream_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        yield "统一"
        yield "模型"


def test_ai_service_uses_unified_llm_client_by_default(monkeypatch):
    import tutor_services

    fake = FakeUnifiedClient()
    monkeypatch.setattr(tutor_services, "create_unified_llm_client", lambda: fake, raising=False)

    service = tutor_services.AIService()

    assert service._client is fake


def test_generation_runner_uses_unified_llm_client(monkeypatch):
    import generation_runner

    fake = FakeUnifiedClient()
    generation_runner._ai_client = None
    monkeypatch.setattr(generation_runner, "create_unified_llm_client", lambda timeout=300: fake, raising=False)

    client = generation_runner._get_ai_client()

    assert client is fake


def test_unified_llm_available_is_quiet_when_rag_service_is_not_ready(monkeypatch, caplog):
    from unified_llm_client import UnifiedLLMClient

    class FailingSession:
        def get(self, *args, **kwargs):
            raise ConnectionError("connection refused")

    client = UnifiedLLMClient("http://localhost:8003")
    client._session = FailingSession()

    assert client.available() is False
    assert "统一 LLM 设置不可用" not in caplog.text


def test_model_info_force_refresh_reloads_8003_settings():
    from unified_llm_client import UnifiedLLMClient

    class Response:
        def __init__(self, model):
            self.model = model

        def raise_for_status(self):
            return None

        def json(self):
            return {"llm": {"provider": "openai-compatible", "model": self.model, "has_api_key": True}}

    class ChangingSession:
        def __init__(self):
            self.models = iter(["old-model", "new-model"])
            self.get_calls = 0

        def get(self, *args, **kwargs):
            self.get_calls += 1
            return Response(next(self.models))

    client = UnifiedLLMClient("http://localhost:8003")
    client._session = ChangingSession()

    assert client.model_info()["model"] == "old-model"
    assert client.model_info()["model"] == "old-model"
    assert client.model_info(refresh=True)["model"] == "new-model"
    assert client._session.get_calls == 2
