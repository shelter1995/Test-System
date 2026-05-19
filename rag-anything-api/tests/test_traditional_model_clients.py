from rag_engines.traditional.model_clients import ModelEndpoint, build_chat_payload, build_embedding_payload, build_rerank_payload


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
