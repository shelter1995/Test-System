"""
AI话术陪练系统 — 数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ==================== 请求模型 ====================

class ScenarioCreate(BaseModel):
    name: str
    ai_role: str
    user_role: str
    description: str
    customer_traits: List[str]
    ai_strategy: List[str]
    success_criteria: List[str]


class SessionStart(BaseModel):
    scenario_id: str
    client_unit: Optional[str] = "某公司"
    product: Optional[str] = "商务视频彩铃"
    scenario_type: Optional[str] = "初次沟通"
    database: Optional[str] = None
    custom_scenario: Optional[ScenarioCreate] = None


class ChatMessage(BaseModel):
    session_id: str
    message: str
    is_pause: bool = False


class SessionEnd(BaseModel):
    session_id: str
    detail_level: str = "simple"


# ==================== SSE 事件类型 ====================

class SSEEvent:
    """SSE 事件的基类，提供标准化格式方法。"""

    @staticmethod
    def format(event: str, data: dict) -> str:
        """格式化为 SSE 标准字符串。"""
        import json
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def status(stage: str, message: str = "", extra: dict = None) -> str:
        """阶段状态事件 (rag_searching / ai_generating / rag_complete)"""
        payload = {"stage": stage, "message": message}
        if extra:
            payload.update(extra)
        return SSEEvent.format("status", payload)

    @staticmethod
    def token(delta: str) -> str:
        """AI 回复的单个 token"""
        return SSEEvent.format("token", {"delta": delta})

    @staticmethod
    def quick_hint(hint: str, hint_type: str = "tip") -> str:
        """快捷评价提示"""
        return SSEEvent.format("quick_hint", {"hint": hint, "type": hint_type})

    @staticmethod
    def evaluation(data: dict) -> str:
        """评估结果"""
        return SSEEvent.format("evaluation", data)

    @staticmethod
    def done(round_num: int, extra: dict = None) -> str:
        """回合完成，释放输入框"""
        payload = {"round": round_num}
        if extra:
            payload.update(extra)
        return SSEEvent.format("done", payload)

    @staticmethod
    def error(message: str, code: str = "unknown") -> str:
        """错误事件"""
        return SSEEvent.format("error", {"message": message, "code": code})
