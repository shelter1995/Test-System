import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tutor_streaming import StreamingPipeline


class FakeRAG:
    def resolve_database(self, product):
        return "kb"

    def search(self, query, database=None, top_k=None):
        return [{"text": "知识片段", "metadata": {"source": "kb.md"}, "score": 1.0}]


class FakeAI:
    def generate_response_stream(self, system_prompt, conversation_history, user_message):
        yield "客户"
        yield "回复"

    def evaluate(self, **kwargs):
        return {"overall_score": 80, "dimension_scores": {}, "feedback": "ok", "suggestions": []}


@pytest.mark.asyncio
async def test_streaming_saves_messages_before_done_event():
    session = {
        "scenario": {"name": "测试场景", "ai_role": "客户", "customer_traits": []},
        "product": "产品",
        "database": "kb",
        "round": 0,
        "messages": [],
        "evaluations": [],
        "client_unit": "客户单位",
        "scenario_type": "价格敏感",
    }
    pipeline = StreamingPipeline(FakeRAG(), FakeAI())

    done_seen = False
    async for event in pipeline.run(session, "你好"):
        if event.startswith("event: done"):
            done_seen = True
            assert session["round"] == 1
            assert session["messages"][0]["role"] == "user"
            assert session["messages"][1]["role"] == "ai"

    assert done_seen is True
