import pytest

from rag_engines.traditional.model_clients import ModelEndpoint, OpenAICompatibleClient, build_chat_payload, build_embedding_payload, build_rerank_payload


def test_build_embedding_payload():
    endpoint = ModelEndpoint(provider="siliconflow", base_url="https://api.siliconflow.cn/v1", api_key="key", model="BAAI/bge-m3")

    payload = build_embedding_payload(endpoint, ["文本A", "文本B"])

    assert payload == {"model": "BAAI/bge-m3", "input": ["文本A", "文本B"]}


def test_build_rerank_payload():
    endpoint = ModelEndpoint(provider="siliconflow", base_url="https://api.siliconflow.cn/v1", api_key="key", model="BAAI/bge-reranker-v2-m3")

    payload = build_rerank_payload(endpoint, "价格", ["价格说明", "开通流程"], top_n=1)

    assert payload["model"] == "BAAI/bge-reranker-v2-m3"
    assert payload["query"] == "价格"
    assert payload["documents"] == ["价格说明", "开通流程"]
    assert payload["top_n"] == 1


def test_build_chat_payload_uses_openai_messages():
    endpoint = ModelEndpoint(provider="minimax", base_url="https://api.minimaxi.com/v1", api_key="key", model="MiniMax-M2.7")

    payload = build_chat_payload(endpoint, system_prompt="你是助手", user_prompt="回答问题")

    assert payload["model"] == "MiniMax-M2.7"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "回答问题"


class FakeResponse:
    def __init__(self, payload, status_code=200, text="", headers=None):
        self._payload = payload
        self.status_code = status_code
        self.reason_phrase = "OK" if status_code < 400 else "Bad Request"
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://example.test")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("bad", request=request, response=response)

    def json(self):
        return self._payload


class FakeAsyncClient:
    calls = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        FakeAsyncClient.calls = []
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        FakeAsyncClient.calls.append(json["input"])
        offset = sum(len(call) for call in FakeAsyncClient.calls[:-1])
        return FakeResponse(
            {
                "data": [
                    {"index": idx, "embedding": [float(offset + idx)]}
                    for idx, _ in enumerate(json["input"])
                ]
            }
        )


@pytest.mark.asyncio
async def test_embed_batches_requests(monkeypatch):
    import rag_engines.traditional.model_clients as model_clients

    monkeypatch.setattr(model_clients.httpx, "AsyncClient", FakeAsyncClient)
    endpoint = ModelEndpoint(
        provider="siliconflow",
        base_url="https://api.siliconflow.cn/v1",
        api_key="key",
        model="BAAI/bge-m3",
        batch_size=2,
    )

    vectors = await OpenAICompatibleClient(endpoint).embed(["a", "b", "c", "d", "e"])

    assert FakeAsyncClient.calls == [["a", "b"], ["c", "d"], ["e"]]
    assert vectors == [[0.0], [1.0], [2.0], [3.0], [4.0]]


class RateLimitedAsyncClient:
    calls = 0

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        RateLimitedAsyncClient.calls = 0
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers, json):
        RateLimitedAsyncClient.calls += 1
        if RateLimitedAsyncClient.calls == 1:
            return FakeResponse(
                {"message": "TPM limit reached"},
                status_code=429,
                text='{"message":"TPM limit reached"}',
                headers={"Retry-After": "1"},
            )
        return FakeResponse({"data": [{"index": 0, "embedding": [1.0]}]})


@pytest.mark.asyncio
async def test_embed_retries_after_rate_limit(monkeypatch):
    import rag_engines.traditional.model_clients as model_clients

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(model_clients.httpx, "AsyncClient", RateLimitedAsyncClient)
    monkeypatch.setattr(model_clients.asyncio, "sleep", fake_sleep)
    endpoint = ModelEndpoint(
        provider="siliconflow",
        base_url="https://api.siliconflow.cn/v1",
        api_key="key",
        model="BAAI/bge-m3",
        retry_attempts=2,
        retry_base_delay=30,
    )

    vectors = await OpenAICompatibleClient(endpoint).embed(["a"])

    assert RateLimitedAsyncClient.calls == 2
    assert sleeps == [1.0]
    assert vectors == [[1.0]]
