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
