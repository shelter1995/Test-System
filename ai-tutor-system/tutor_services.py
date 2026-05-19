"""
AI话术陪练系统 — 业务服务层
无状态服务类，可独立测试。
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

import requests

import tutor_config as config
from minimax_client import MiniMaxClient
from rag_client import RAGClient, get_rag_client

try:
    from json_repair import repair_json
except ImportError:  # pragma: no cover - optional dependency
    repair_json = None

logger = logging.getLogger(__name__)

EVALUATION_DIMENSION_NAMES = [
    item.get("name", key)
    for key, item in getattr(config, "EVALUATION_DIMENSIONS", {}).items()
]
if not EVALUATION_DIMENSION_NAMES:
    EVALUATION_DIMENSION_NAMES = [
        "开场话术",
        "需求挖掘",
        "产品介绍",
        "异议处理",
        "促成技巧",
    ]


def _extract_json_object(text: str) -> dict:
    """Extract the first complete JSON object from an LLM response."""
    raw = str(text or "").strip()
    if "```json" in raw:
        raw = raw.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in raw:
        raw = raw.split("```", 1)[1].split("```", 1)[0].strip()

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in AI response")

    decoder = json.JSONDecoder()
    json_text = raw[start:]
    try:
        obj, _ = decoder.raw_decode(json_text)
    except json.JSONDecodeError:
        if repair_json is None:
            raise
        obj = repair_json(json_text, return_objects=True)

    if not isinstance(obj, dict):
        raise ValueError("AI response JSON is not an object")
    return obj


def _clamp_score(value: Any, default: int = 70) -> int:
    try:
        if isinstance(value, str):
            value = value.strip().replace("分", "")
        score = round(float(value))
    except (TypeError, ValueError):
        score = default
    return max(0, min(100, score))


def _normalize_suggestions(value: Any, default: Optional[List[str]] = None) -> List[str]:
    if default is None:
        default = []
    if not isinstance(value, list):
        return default
    suggestions = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in suggestions:
            suggestions.append(text)
    return suggestions


def _normalize_dimension_scores(value: Any, fallback_score: int = 70) -> Dict[str, Dict]:
    dimensions = value if isinstance(value, dict) else {}
    normalized: Dict[str, Dict] = {}
    for name in EVALUATION_DIMENSION_NAMES:
        raw = dimensions.get(name, {})
        if isinstance(raw, dict):
            score = _clamp_score(raw.get("score"), fallback_score)
            feedback = str(raw.get("feedback") or "").strip()
        else:
            score = _clamp_score(raw, fallback_score)
            feedback = ""
        if not feedback:
            feedback = "本轮该维度信息不足，按基准分处理。"
        normalized[name] = {"score": score, "feedback": feedback}
    return normalized


def _normalize_evaluation(value: Any, fallback_score: int = 70) -> Dict[str, Any]:
    evaluation = value if isinstance(value, dict) else {}
    dims = _normalize_dimension_scores(
        evaluation.get("dimension_scores"), fallback_score=fallback_score
    )
    raw_total = evaluation.get("overall_score", evaluation.get("total_score"))
    if raw_total is None and dims:
        raw_total = round(
            sum(item["score"] for item in dims.values()) / len(dims)
        )
    overall_score = _clamp_score(raw_total, fallback_score)
    feedback = str(evaluation.get("feedback") or "").strip()
    if not feedback:
        feedback = "本轮已完成评分。"
    suggestions = _normalize_suggestions(
        evaluation.get("suggestions"),
        ["下一轮继续围绕客户需求给出更具体的证据和推进动作。"],
    )
    return {
        "overall_score": overall_score,
        "dimension_scores": dims,
        "feedback": feedback,
        "suggestions": suggestions,
    }


# ==================== RAGService ====================

class RAGService:
    """Knowledge base search service wrapping RAG-Anything API."""

    PRODUCT_TO_DATABASE = {}

    def __init__(self, rag_client: RAGClient = None):
        self._client = rag_client

    @property
    def client(self) -> RAGClient:
        if self._client is None:
            self._client = get_rag_client()
        return self._client

    def resolve_database(self, product: str | None) -> str | None:
        """Resolve knowledge base name from product name. Falls back to default."""
        key = str(product or "").strip()
        if key in self.PRODUCT_TO_DATABASE:
            return self.PRODUCT_TO_DATABASE[key]
        default_db = str(getattr(config, "DEFAULT_RAG_DATABASE", "") or "").strip()
        return default_db or None

    def search(
        self, query: str, database: str = None, top_k: int = None
    ) -> List[Dict]:
        """
        Search RAG knowledge base.
        Returns: [{"text": "...", ...}, ...]
        """
        if top_k is None:
            top_k = config.RAG_TOP_K

        try:
            params = {"query": query, "n_results": top_k}
            if database:
                params["database"] = database

            endpoint = "context" if database else "ai_enhanced_search"
            response = requests.post(
                f"{config.RAG_SERVICE_URL}/{endpoint}",
                json=params,
                timeout=config.RAG_REQUEST_TIMEOUT,
            )

            # Missing or stale database selection: fall back to all registered databases.
            if response.status_code == 404 and database:
                logger.warning(
                    "RAG database '%s' not found for endpoint /%s; falling back to all databases",
                    database,
                    endpoint,
                )
                fallback_params = {"query": query, "n_results": top_k}
                response = requests.post(
                    f"{config.RAG_SERVICE_URL}/ai_enhanced_search",
                    json=fallback_params,
                    timeout=config.RAG_REQUEST_TIMEOUT,
                )

            if response.status_code == 200:
                data = response.json()
                results = data.get("contexts", data.get("results", []))
                logger.info(
                    "RAG search: '%s' -> db: %s -> %d results",
                    query, database or "default", len(results)
                )
                return results
            else:
                logger.warning(
                    "RAG search failed: HTTP %d, endpoint=/%s, database=%s, body=%s",
                    response.status_code,
                    endpoint,
                    database or "all",
                    response.text[:300],
                )
                return []
        except Exception as e:
            logger.error("RAG search error: %s", e)
            return []


# ==================== AIService ====================

class AIService:
    """AI generation service wrapping MiniMax streaming and non-streaming calls."""

    def __init__(self, client: MiniMaxClient = None):
        if client is not None:
            self._client = client
        else:
            self._client = MiniMaxClient(
                api_key=config.MINIMAX_API_KEY,
                model=config.MINIMAX_MODEL,
            )

    @property
    def available(self) -> bool:
        return bool(
            config.MINIMAX_API_KEY
            and config.MINIMAX_API_KEY != "your_minimax_api_key_here"
        )

    def generate_response(
        self,
        system_prompt: str,
        conversation_history: List[Dict],
        user_message: str,
    ) -> str:
        """Non-streaming AI response generation (backward compat for /chat)."""
        if not self.available:
            return "抱歉，AI服务未配置。请在tutor_config.py中设置MINIMAX_API_KEY。"

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                *conversation_history,
                {"role": "user", "content": user_message},
            ]
            result = self._client.chat_completion(
                messages=messages,
                temperature=0.8,
                max_tokens=800,
            )
            if result["success"]:
                content = result["content"]
                logger.info("AI generated response: %s...", content[:100])
                return content
            else:
                logger.error("AI generation failed: %s", result.get("error", ""))
                return "Sorry, AI service temporarily unavailable."
        except Exception as e:
            logger.error("AI generation exception: %s", e)
            return "Sorry, AI service temporarily unavailable."

    def generate_response_stream(
        self,
        system_prompt: str,
        conversation_history: List[Dict],
        user_message: str,
    ):
        """Streaming AI response generation (for /chat/stream endpoint).

        Yields:
            str: token delta
        """
        if not self.available:
            yield "Sorry, AI service not configured."
            return

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                *conversation_history,
                {"role": "user", "content": user_message},
            ]
            for token in self._client.stream_chat_completion(
                messages=messages,
                temperature=0.8,
                max_tokens=800,
            ):
                yield token
        except Exception as e:
            logger.error("AI streaming exception: %s", e)
            yield "\n\n[AI response interrupted, please retry]"

    def evaluate(
        self,
        user_message: str,
        ai_response: str,
        round_num: int,
        scenario: dict,
        knowledge_context: str,
        database: str = None,
    ) -> Dict[str, Any]:
        """Evaluate user's sales pitch. Returns score + suggestions."""
        if not self.available:
            return self._fallback_evaluation("AI服务未配置，使用默认基准评分。")

        # Search for evaluation standards
        eval_knowledge = RAGService().search(
            f"销售话术评估标准 {scenario.get('name', '')}",
            top_k=3,
            database=database,
        )

        kb_info = ""
        if eval_knowledge:
            kb_info = "\n\nEvaluation standards from knowledge base:\n" + "\n".join(
                [f"- {item['text']}" for item in eval_knowledge]
            )

        prompt = f"""你是一位专业的销售培训师，请评估销售代表刚才的话术。你必须用中文输出所有文字。

【评估原则】
1. 评估必须基于知识库中的销售方法论和标准
2. 如果知识库中没有相关标准，基于行业最佳实践
3. 客观、具体、有建设性
4. 每个维度的 feedback 字段必须写出具体评分依据，说明为什么给这个分数

【对话上下文】
- 轮次：第{round_num}轮
- 场景：{scenario.get('name', '')}
- 客户角色：{scenario.get('ai_role', '')}
- 销售代表说：{user_message}
- 客户回应：{ai_response}
{kb_info}

返回纯 JSON（不要 markdown 代码块），所有文字用中文：
{{
    "overall_score": <总分 0-100>,
    "dimension_scores": {{
        "开场话术": {{"score": <0-100>, "feedback": "<评分依据和具体建议>"}},
        "需求挖掘": {{"score": <0-100>, "feedback": "<评分依据和具体建议>"}},
        "产品介绍": {{"score": <0-100>, "feedback": "<评分依据和具体建议>"}},
        "异议处理": {{"score": <0-100>, "feedback": "<评分依据和具体建议>"}},
        "促成技巧": {{"score": <0-100>, "feedback": "<评分依据和具体建议>"}}
    }},
    "feedback": "<整体评价，中文>",
    "suggestions": ["<改进建议1>", "<改进建议2>", "<改进建议3>"]
}}

只返回 JSON，不要其他内容。"""

        try:
            result = self._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1800,
            )
            if not result["success"]:
                return self._fallback_evaluation()

            try:
                evaluation = _extract_json_object(result["content"])
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "AI evaluation JSON parse failed: %s; using fallback evaluation",
                    e,
                )
                return self._fallback_evaluation()
            evaluation = _normalize_evaluation(evaluation)
            logger.info(
                "AI evaluation complete: score %s", evaluation.get("overall_score", 0)
            )
            return evaluation
        except Exception as e:
            logger.error("AI evaluation exception: %s; using fallback evaluation", e)
            return self._fallback_evaluation()

    def _fallback_evaluation(self, feedback: str = "评估服务暂时不可用") -> dict:
        return _normalize_evaluation(
            {
                "overall_score": 70,
                "dimension_scores": {},
                "feedback": feedback,
                "suggestions": ["建议下一轮围绕客户需求、产品价值和推进动作给出更具体表达。"],
            }
        )

    def generate_opening(
        self,
        scenario: dict,
        client_unit: str,
        product: str,
        scenario_type: str,
        database: str = None,
    ) -> str:
        """Generate AI opening line."""
        if not self.available:
            return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"

        rag = RAGService()
        product_knowledge = rag.search(
            f"{product} 产品介绍", top_k=3, database=database
        )
        opening_knowledge = rag.search(
            f"{scenario.get('name', '')} 开场话术 初次沟通",
            top_k=3,
            database=database,
        )

        knowledge_context = ""
        if product_knowledge or opening_knowledge:
            knowledge_context = "\n\n【知识库相关信息】\n"
            if product_knowledge:
                knowledge_context += "\n产品信息：\n" + "\n".join(
                    [f"- {item['text']}" for item in product_knowledge]
                )
            if opening_knowledge:
                knowledge_context += "\n开场话术参考：\n" + "\n".join(
                    [f"- {item['text']}" for item in opening_knowledge]
                )

        prompt = f"""你现在是【{scenario['ai_role']}】，来自{client_unit}，与销售代表初次沟通。必须用中文。

【角色约束】
- 性格：{', '.join(scenario.get('customer_traits', ['专业、谨慎']))}
- 倾向：{', '.join(scenario.get('ai_strategy', ['了解产品']))}
- 不要给自己起具体姓名（如"李总"），用"我"自称

【关键规则】
1. 只能使用知识库中的产品信息
2. 禁止编造产品功能、价格
3. 像真实的{scenario['ai_role']}一样自然说话
4. 展现真实的兴趣或疑问

【场景】
- 单位：{client_unit}
- 产品：{product}
- 背景：{scenario_type}
{knowledge_context}

用自然的中文说出开场白。只输出开场白，不要解释。"""

        try:
            result = self._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=300,
            )
            if result["success"]:
                return result["content"]
            return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"
        except Exception:
            return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"


# ==================== SessionManager ====================

class SessionManager:
    """Session lifecycle management."""

    @staticmethod
    def generate_id() -> str:
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    def save(session_id: str, session_data: dict) -> None:
        try:
            session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            logger.info("Session saved: %s", session_id)
        except Exception as e:
            logger.error("Failed to save session: %s", e)

    @staticmethod
    def load(session_id: str) -> Optional[dict]:
        try:
            session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
            if session_file.exists():
                with open(session_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error("Failed to load session: %s", e)
        return None

    @staticmethod
    def list_all() -> List[dict]:
        """List all historical sessions."""
        sessions_dir = Path(config.SESSIONS_DIR)
        history = []
        for session_file in sessions_dir.glob("*.json"):
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            report = session_data.get("report", {})
            history.append(
                {
                    "session_id": session_data["session_id"],
                    "scenario": session_data["scenario"]["name"],
                    "rounds": session_data["round"],
                    "status": session_data["status"],
                    "created_at": session_data["created_at"],
                    "client_unit": session_data.get("client_unit", ""),
                    "product": session_data.get("product", ""),
                    "score": report.get("total_score"),
                    "rating": report.get("rating_text"),
                }
            )
        history.sort(key=lambda x: x["created_at"], reverse=True)
        return history


# ==================== ReportGenerator ====================

class ReportGenerator:
    """Final evaluation report generation."""

    def __init__(self, ai_service: AIService = None):
        self._ai = ai_service or AIService()

    def generate(self, session_data: dict) -> dict:
        """Generate final evaluation report."""
        if session_data.get("evaluations"):
            return self._from_evaluations(session_data)

        if not self._ai.available:
            return self._fallback(session_data)

        messages = session_data.get("messages", [])
        scenario = session_data.get("scenario", {})
        rounds = session_data.get("round", 0)
        product = session_data.get("product", "")
        database = session_data.get("database") or RAGService().resolve_database(
            product
        )

        training_standards = RAGService().search(
            "销售培训标准 评估方法 销售方法论",
            top_k=5,
            database=database,
        )

        kb_ctx = ""
        if training_standards:
            kb_ctx = "\n\n[Training Standards from KB]\n" + "\n".join(
                [f"- {item['text']}" for item in training_standards]
            )
        else:
            kb_ctx = "\n\n[Note] No training standards in KB, use industry best practices."

        # Build conversation summary
        conv_summary = ""
        for msg in messages[-10:]:
            role = "Customer" if msg.get("role") == "ai" else "Sales Rep"
            conv_summary += f"\n{role}: {msg.get('content', '')}\n"

        prompt = f"""你是一位资深的销售培训专家，请对这场销售陪练对话进行总结评估。所有文字必须用中文输出。

【评估原则】
1. 评估标准应来自知识库中的销售培训方法论
2. 不能编造评估方法
3. 如果知识库没有相关标准，如实说明

【会话信息】
- 场景：{scenario.get('name', '')}
- 总轮次：{rounds}
- 客户单位：{session_data.get('client_unit', '')}
- 产品：{session_data.get('product', '')}

【对话摘要】
{conv_summary}
{kb_ctx}

返回纯 JSON（不要 markdown 代码块），所有文字用中文：
{{
    "total_score": <总分 0-100>,
    "rating_text": "<评级：优秀/良好/满意/待改进/较差>",
    "dimension_scores": {{
        "开场话术": {{"score": <0-100>, "feedback": "<中文评价>"}},
        "需求挖掘": {{"score": <0-100>, "feedback": "<中文评价>"}},
        "产品介绍": {{"score": <0-100>, "feedback": "<中文评价>"}},
        "异议处理": {{"score": <0-100>, "feedback": "<中文评价>"}},
        "促成技巧": {{"score": <0-100>, "feedback": "<中文评价>"}}
    }},
    "highlights": ["<亮点1>", "<亮点2>", "<亮点3>"],
    "improvements": ["<待改进1>", "<待改进2>", "<待改进3>"],
    "suggestions": ["<建议1>", "<建议2>", "<建议3>"]
}}

只返回 JSON，不要其他内容。"""

        try:
            result = self._ai._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            if not result["success"]:
                return self._fallback(session_data)

            try:
                report = _extract_json_object(result["content"])
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Report JSON parse failed: %s; using fallback report",
                    e,
                )
                return self._fallback(session_data)
            report = self._normalize_report(report, session_data)
            for field in ["highlights", "improvements", "suggestions"]:
                report.setdefault(field, [])
            return report
        except Exception as e:
            logger.error("Report generation exception: %s", e)
            return self._fallback(session_data)

    def _from_evaluations(self, session_data: dict) -> dict:
        """Build a fast deterministic report from completed round evaluations."""
        evals = [
            _normalize_evaluation(ev)
            for ev in session_data.get("evaluations", [])
            if isinstance(ev, dict)
        ]
        if not evals:
            return self._fallback(session_data)

        total_score = round(
            sum(ev["overall_score"] for ev in evals) / len(evals)
        )
        dimension_scores: Dict[str, Dict] = {}
        for name in EVALUATION_DIMENSION_NAMES:
            scores = [
                ev["dimension_scores"][name]["score"]
                for ev in evals
                if name in ev.get("dimension_scores", {})
            ]
            avg_score = round(sum(scores) / len(scores)) if scores else 70
            feedbacks = []
            for ev in evals[-3:]:
                feedback = ev.get("dimension_scores", {}).get(name, {}).get("feedback", "")
                if feedback and feedback not in feedbacks:
                    feedbacks.append(feedback)
            dimension_scores[name] = {
                "score": avg_score,
                "feedback": "；".join(feedbacks[:2])
                or "该维度已按逐轮评分汇总。",
            }

        strong_dims = [
            name for name, data in dimension_scores.items() if data["score"] >= 80
        ]
        weak_dims = [
            name for name, data in dimension_scores.items() if data["score"] < 70
        ]
        rounds = session_data.get("round", len(evals))
        highlights = [f"完成了 {rounds} 轮对话练习"]
        if strong_dims:
            highlights.append(f"{strong_dims[0]}表现相对稳定")
        if total_score >= 80:
            highlights.append("整体话术达到了较好的训练水平")

        improvements = []
        for name in weak_dims[:3]:
            improvements.append(f"需要继续加强{name}")
        if not improvements:
            improvements.append("继续提升表达的针对性和成交推进节奏")

        suggestions = []
        for ev in evals:
            for item in ev.get("suggestions", []):
                text = str(item or "").strip()
                if text and text not in suggestions:
                    suggestions.append(text)
        if not suggestions:
            suggestions = [
                "后续练习中先确认客户真实需求，再结合产品价值给出证据。",
                "遇到异议时先复述客户顾虑，再给出案例或数据支撑。",
                "每轮结尾增加明确的下一步推进动作。",
            ]

        return {
            "total_score": total_score,
            "rating_text": self._to_rating(total_score),
            "dimension_scores": dimension_scores,
            "highlights": highlights[:3],
            "improvements": improvements[:3],
            "suggestions": suggestions[:5],
        }

    def _normalize_report(self, report: dict, session_data: dict) -> dict:
        total_score = _clamp_score(
            report.get("total_score", report.get("overall_score")),
            self._calc_avg(session_data),
        )
        return {
            "total_score": total_score,
            "rating_text": str(report.get("rating_text") or self._to_rating(total_score)),
            "dimension_scores": _normalize_dimension_scores(
                report.get("dimension_scores"), fallback_score=total_score
            ),
            "highlights": _normalize_suggestions(report.get("highlights")),
            "improvements": _normalize_suggestions(report.get("improvements")),
            "suggestions": _normalize_suggestions(report.get("suggestions")),
        }

    def _fallback(self, session_data: dict) -> dict:
        """Fallback report when AI unavailable."""
        evals = session_data.get("evaluations", [])
        avg = self._calc_avg(session_data)
        rounds = session_data.get("round", 0)

        all_suggestions = []
        for ev in evals:
            for s in ev.get("suggestions", []):
                if s and s not in all_suggestions:
                    all_suggestions.append(s)

        highlights = [f"完成了 {rounds} 轮对话练习"]
        improvements = []
        if avg >= 80:
            highlights.append("整体表现良好")
        elif avg < 60:
            improvements.append("建议加强练习，提升话术熟练度")

        return {
            "total_score": avg,
            "rating_text": self._to_rating(avg),
            "dimension_scores": _normalize_dimension_scores({}, fallback_score=avg),
            "highlights": highlights,
            "improvements": improvements or ["继续保持练习"],
            "suggestions": all_suggestions[:5]
            or ["建议多练习产品介绍和异议处理话术"],
        }

    @staticmethod
    def _calc_avg(session_data: dict) -> int:
        evals = session_data.get("evaluations", [])
        if evals:
            scores = [
                e.get("overall_score", 0)
                for e in evals
                if e.get("overall_score", 0) > 0
            ]
            return round(sum(scores) / len(scores)) if scores else 70
        return 70

    @staticmethod
    def _to_rating(score: int) -> str:
        if score >= 90:
            return "优秀"
        elif score >= 80:
            return "良好"
        elif score >= 70:
            return "满意"
        elif score >= 60:
            return "待改进"
        return "较差"


# ==================== Context prompt helper ====================


def build_rag_context_prompt(context_result: dict) -> str:
    contexts = context_result.get("contexts") or []
    if not contexts:
        return ""
    lines = ["可参考的知识库资料："]
    for item in contexts:
        metadata = item.get("metadata") or {}
        source = metadata.get("source", "unknown")
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(f"- 来源 {source}: {text}")
    return "\n".join(lines)


# ==================== Convenience singletons ====================

_default_rag: Optional[RAGService] = None
_default_ai: Optional[AIService] = None


def get_rag_service() -> RAGService:
    global _default_rag
    if _default_rag is None:
        _default_rag = RAGService()
    return _default_rag


def get_ai_service() -> AIService:
    global _default_ai
    if _default_ai is None:
        _default_ai = AIService()
    return _default_ai
