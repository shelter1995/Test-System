from fastapi.testclient import TestClient

import app as rag_api
from kb_answer import build_kb_answer_prompt, extract_source_summaries


def test_extract_source_summaries_includes_extended_fields():
    contexts = [
        {
            "text": "商务彩铃基础版 10 元/月/线。",
            "score": 0.91,
            "rerank_score": 0.98,
            "source_id": "来源 1",
            "chunk_index": 3,
            "document_sha256": "abc123",
            "metadata": {
                "source": "资费说明.pdf",
                "engine": "traditional",
            },
        }
    ]

    sources = extract_source_summaries(contexts)

    assert sources == [
        {
            "source_id": "来源 1",
            "file_name": "资费说明.pdf",
            "snippet": "商务彩铃基础版 10 元/月/线。",
            "score": 0.91,
            "rerank_score": 0.98,
            "chunk_index": 3,
            "document_sha256": "abc123",
            "engine": "traditional",
        }
    ]


def test_build_kb_answer_prompt_requires_source_citation_and_conclusion_first():
    prompt = build_kb_answer_prompt(
        query="资费是多少",
        contexts=[
            {
                "text": "商务彩铃基础版 10 元/月/线。",
                "source_id": "来源 1",
                "metadata": {"source": "资费说明.pdf"},
                "score": 0.92,
            }
        ],
        history=[{"q": "有优惠吗", "a": "请看套餐活动"}],
    )

    assert "关键句后标注来源编号（如 [来源 1]）" in prompt
    assert "先给出结论，再给出依据" in prompt
    assert "资料不足时明确说明信息缺口" in prompt
    assert "[来源 1｜来源：资费说明.pdf]" in prompt


def test_kb_chat_prefers_retrieve_contexts_with_history(monkeypatch):
    observed = {"retrieve_history": None, "query_context_called": False}

    class FakeEngine:
        async def retrieve_contexts(self, db_id, query, history=None):
            observed["retrieve_history"] = history
            return [
                {
                    "text": "商务彩铃基础版 10 元/月/线。",
                    "source_id": "来源 1",
                    "score": 0.9,
                    "metadata": {"source": "资费说明.pdf", "engine": "traditional"},
                }
            ]

        async def query_context(self, *args, **kwargs):
            observed["query_context_called"] = True
            return {"contexts": []}

    class FakeService:
        async def generate_answer(self, prompt):
            return "结论：10 元/月/线 [来源 1]"

    monkeypatch.setattr(rag_api, "_require_service", lambda: FakeService())
    monkeypatch.setattr(rag_api, "_engine_for_database", lambda _db_id: FakeEngine())

    client = TestClient(rag_api.app)
    response = client.post(
        "/kb/chat",
        json={
            "query": "资费是多少",
            "database": "商务彩铃",
            "history": [{"q": "上个问题", "a": "上个回答"}],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert observed["retrieve_history"] == [{"q": "上个问题", "a": "上个回答"}]
    assert observed["query_context_called"] is False
    assert data["sources"][0]["source_id"] == "来源 1"

