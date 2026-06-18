import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from thought_filter import ThoughtTokenFilter, strip_thought_content
from tutor_streaming import StreamingPipeline, _build_system_prompt


class FakeRAG:
    def __init__(self):
        self.queries = []

    def resolve_database(self, product):
        return "kb"

    def search(self, query, database=None, top_k=None):
        self.queries.append(query)
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


@pytest.mark.asyncio
async def test_streaming_searches_government_decision_context():
    session = {
        "scenario": {"name": "政企高层汇报场景", "ai_role": "分管领导", "customer_traits": []},
        "product": "小微ICT",
        "database": "kb",
        "round": 0,
        "messages": [],
        "evaluations": [],
        "client_unit": "某区县政务中心",
        "scenario_type": "专项工作优化座谈",
    }
    rag = FakeRAG()
    pipeline = StreamingPipeline(rag, FakeAI())

    async for _event in pipeline.run(session, "我们的小微ICT价格很优惠"):
        pass

    joined = "\n".join(rag.queries)
    assert "政策 考核 风险 高层汇报" in joined
    assert "销售技巧" in joined


def test_system_prompt_models_government_decision_maker_logic():
    prompt = _build_system_prompt(
        scenario={"name": "政企高层汇报场景", "ai_role": "分管领导", "customer_traits": []},
        client_unit="某区县政务中心",
        product="小微ICT",
        scenario_type="专项工作优化座谈",
        round_num=1,
        knowledge_context="资料",
    )

    assert "适用政企或高层客户时" in prompt
    assert "政策依据、考核价值、风险控制" in prompt
    assert "不要脱离知识库" in prompt


class ThinkTokenAI:
    def generate_response_stream(self, system_prompt, conversation_history, user_message):
        yield "<thi"
        yield "nk>内部分析"
        yield "，不要展示</think>嗯，"
        yield "我想了解一下。"


@pytest.mark.asyncio
async def test_streaming_filters_think_tokens_from_events_and_saved_message():
    session = {
        "scenario": {"name": "测试场景", "ai_role": "客户", "customer_traits": []},
        "product": "产品",
        "database": "kb",
        "round": 0,
        "messages": [],
        "evaluations": [],
        "client_unit": "客户单位",
        "scenario_type": "初次沟通",
    }
    pipeline = StreamingPipeline(FakeRAG(), ThinkTokenAI())

    events = []
    async for event in pipeline.run(session, "你好"):
        events.append(event)

    rendered = "\n".join(events)
    saved_ai_message = session["messages"][1]["content"]
    assert "<think>" not in rendered
    assert "内部分析" not in rendered
    assert saved_ai_message == "嗯，我想了解一下。"


def test_strip_thought_content_removes_complete_and_unterminated_reasoning():
    assert strip_thought_content("<think>内部分析</think>客户回复") == "客户回复"
    assert strip_thought_content("可见内容<thinking>未结束分析") == "可见内容"


def test_thought_filter_preserves_non_reasoning_angle_brackets():
    filter_ = ThoughtTokenFilter()
    assert filter_.feed("价格 < 100 元") + filter_.flush() == "价格 < 100 元"
