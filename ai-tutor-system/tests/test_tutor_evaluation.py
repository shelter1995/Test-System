import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from tutor_services import AIService, EVALUATION_DIMENSION_NAMES, ReportGenerator


class FakeMiniMaxClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "content": self.content}


@patch("tutor_services.config.MINIMAX_API_KEY", "test-key")
@patch("tutor_services.RAGService.search", return_value=[])
def test_evaluation_repairs_bad_json_and_fills_all_dimensions(_mock_search):
    content = """{
        "overall_score": 82
        "dimension_scores": {
            "开场话术": {"score": 80, "feedback": "开场自然"},
            "需求挖掘": {"score": 78, "feedback": "有需求确认"}
        },
        "feedback": "整体表现稳定",
        "suggestions": ["继续加强异议处理"]
    }"""
    service = AIService(client=FakeMiniMaxClient(content))

    result = service.evaluate(
        user_message="我们可以先了解一下您的使用场景。",
        ai_response="我主要关心实际效果。",
        round_num=1,
        scenario={"name": "竞品对比型客户", "ai_role": "客户"},
        knowledge_context="",
    )

    assert result["overall_score"] == 82
    assert set(result["dimension_scores"]) == set(EVALUATION_DIMENSION_NAMES)
    assert result["dimension_scores"]["开场话术"]["score"] == 80
    assert all(
        item["feedback"] for item in result["dimension_scores"].values()
    )


def test_report_uses_existing_round_evaluations_with_full_dimensions():
    generator = ReportGenerator(ai_service=object())
    session_data = {
        "round": 2,
        "evaluations": [
            {
                "overall_score": 80,
                "dimension_scores": {
                    "开场话术": {"score": 85, "feedback": "开场清晰"},
                    "需求挖掘": {"score": 75, "feedback": "问题较具体"},
                },
                "suggestions": ["补充客户案例"],
            },
            {
                "overall_score": 70,
                "dimension_scores": {
                    "开场话术": {"score": 75, "feedback": "延续沟通"},
                    "异议处理": {"score": 65, "feedback": "回应还不够充分"},
                },
                "suggestions": ["明确下一步动作"],
            },
        ],
    }

    report = generator.generate(session_data)

    assert report["total_score"] == 75
    assert report["rating_text"] == "满意"
    assert set(report["dimension_scores"]) == set(EVALUATION_DIMENSION_NAMES)
    assert report["dimension_scores"]["开场话术"]["score"] == 80
    assert "补充客户案例" in report["suggestions"]
    assert "明确下一步动作" in report["suggestions"]


@patch("tutor_services.RAGService.search", return_value=[])
def test_evaluation_prompt_scores_government_decision_value(_mock_search):
    client = FakeMiniMaxClient(
        """{
            "overall_score": 76,
            "dimension_scores": {},
            "feedback": "需要提升高层价值表达",
            "suggestions": ["补充政策依据和风险管控"]
        }"""
    )
    service = AIService(client=client)

    service.evaluate(
        user_message="我们的小微ICT功能很多，价格也可以优惠。",
        ai_response="我更关心这个项目对年度考核和风险有没有帮助。",
        round_num=1,
        scenario={"name": "政企高层汇报场景", "ai_role": "分管领导"},
        knowledge_context="",
        database="kb",
    )

    prompt = client.calls[0]["messages"][0]["content"]
    assert "适用政企或高层场景时" in prompt
    assert "政策依据、考核价值、风险控制" in prompt
    assert "不能因为没提这些内容而机械扣分" in prompt


@patch("tutor_services.RAGService.search", return_value=[])
def test_non_streaming_response_hides_reasoning(_mock_search):
    client = FakeMiniMaxClient("<think>内部分析</think>客户回复")
    service = AIService(client=client)

    result = service.generate_response(
        system_prompt="系统提示",
        conversation_history=[],
        user_message="你好",
    )

    assert result == "客户回复"
