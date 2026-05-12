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

logger = logging.getLogger(__name__)


# ==================== RAGService ====================

class RAGService:
    """Knowledge base search service wrapping RAG-Anything API."""

    PRODUCT_TO_DATABASE = {
        "商务视频彩铃": "商务彩铃",
        "视频彩铃": "商务彩铃",
        "商务彩铃": "商务彩铃",
    }

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

            # context endpoint not found? fallback to ai_enhanced_search
            if response.status_code == 404 and endpoint == "context":
                response = requests.post(
                    f"{config.RAG_SERVICE_URL}/ai_enhanced_search",
                    json=params,
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
                logger.warning("RAG search failed: HTTP %d", response.status_code)
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
            return "Sorry, AI service not configured. Set MINIMAX_API_KEY in tutor_config.py."

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
            return {
                "overall_score": 70,
                "dimension_scores": {},
                "feedback": "AI service not configured",
                "suggestions": [],
            }

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

        prompt = f"""You are a professional sales trainer. Evaluate the sales rep's pitch.

[Important]
1. Evaluation must be based on knowledge base standards
2. If no standards in KB, use industry best practices
3. Be objective, specific, constructive

[Context]
- Round: {round_num}
- Scenario: {scenario.get('name', '')}
- AI Role: {scenario.get('ai_role', '')}
- Sales rep said: {user_message}
- AI customer responded: {ai_response}
{kb_info}

Return JSON:
{{
    "overall_score": <0-100>,
    "dimension_scores": {{
        "开场话术": {{"score": <int>, "feedback": "<text>"}},
        "需求挖掘": {{"score": <int>, "feedback": "<text>"}},
        "产品介绍": {{"score": <int>, "feedback": "<text>"}},
        "异议处理": {{"score": <int>, "feedback": "<text>"}},
        "促成技巧": {{"score": <int>, "feedback": "<text>"}}
    }},
    "feedback": "<overall>",
    "suggestions": ["<tip1>", "<tip2>", "<tip3>"]
}}

Return ONLY JSON, nothing else."""

        try:
            result = self._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )
            if not result["success"]:
                return self._fallback_evaluation()

            text = result["content"]
            # Extract JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if not text.startswith("{"):
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    text = text[start : end + 1]

            evaluation = json.loads(text)
            logger.info(
                "AI evaluation complete: score %s", evaluation.get("overall_score", 0)
            )
            return evaluation
        except Exception as e:
            logger.error("AI evaluation exception: %s", e)
            return self._fallback_evaluation()

    def _fallback_evaluation(self) -> dict:
        return {
            "overall_score": 70,
            "dimension_scores": {},
            "feedback": "Evaluation service temporarily unavailable",
            "suggestions": [],
        }

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
            return (
                f"Hello, I'm {scenario['ai_role']} from {client_unit}. "
                f"I heard you have {product} products?"
            )

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
            knowledge_context = "\n\n[Knowledge Base Info]\n"
            if product_knowledge:
                knowledge_context += "\nProduct info:\n" + "\n".join(
                    [f"- {item['text']}" for item in product_knowledge]
                )
            if opening_knowledge:
                knowledge_context += "\nOpening reference:\n" + "\n".join(
                    [f"- {item['text']}" for item in opening_knowledge]
                )

        prompt = f"""You are fully immersed in the role of [{scenario['ai_role']}], speaking as a real customer from {client_unit} in an initial meeting.

[Character Traits]
- Personality: {', '.join(scenario.get('customer_traits', ['professional, cautious']))}
- Approach: {', '.join(scenario.get('ai_strategy', ['learn about product']))}

[Key Rules]
1. Only use product info from the knowledge base
2. Don't make up features, prices, or capabilities
3. Speak naturally, like a real {scenario['ai_role']}
4. Show genuine curiosity or concerns

[Scene]
- Unit: {client_unit}
- Product: {product}
- Context: {scenario_type}
{knowledge_context}

Speak as {scenario['ai_role']} with natural, authentic language. Just the opening line, no explanation."""

        try:
            result = self._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=300,
            )
            if result["success"]:
                return result["content"]
            return (
                f"Hello, I'm {scenario['ai_role']} from {client_unit}. "
                f"I heard you have {product} products?"
            )
        except Exception:
            return (
                f"Hello, I'm {scenario['ai_role']} from {client_unit}. "
                f"I heard you have {product} products?"
            )


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
        """Generate final evaluation report using AI."""
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

        prompt = f"""You are a senior sales training expert. Summarize and evaluate this coaching conversation.

[Important]
1. Standards must come from KB training methodology
2. Don't fabricate evaluation methods
3. State clearly if KB has no relevant standards

[Session Info]
- Scenario: {scenario.get('name', '')}
- Rounds: {rounds}
- Client: {session_data.get('client_unit', '')}
- Product: {session_data.get('product', '')}

[Conversation Summary]
{conv_summary}
{kb_ctx}

Return JSON:
{{
    "total_score": <0-100>,
    "rating_text": "<Excellent/Good/Satisfactory/Needs Improvement/Poor>",
    "dimension_scores": {{}},
    "highlights": ["<highlight1>", "<highlight2>", "<highlight3>"],
    "improvements": ["<area1>", "<area2>", "<area3>"],
    "suggestions": ["<tip1>", "<tip2>", "<tip3>"]
}}

Return ONLY JSON."""

        try:
            result = self._ai._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            if not result["success"]:
                return self._fallback(session_data)

            text = result["content"]
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if not text.startswith("{"):
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    text = text[start : end + 1]

            report = json.loads(text)
            report.setdefault("total_score", self._calc_avg(session_data))
            report.setdefault("rating_text", self._to_rating(report["total_score"]))
            for field in ["highlights", "improvements", "suggestions"]:
                report.setdefault(field, [])
            return report
        except Exception as e:
            logger.error("Report generation exception: %s", e)
            return self._fallback(session_data)

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

        highlights = [f"Completed {rounds} rounds of practice"]
        improvements = []
        if avg >= 80:
            highlights.append("Good performance")
        elif avg < 60:
            improvements.append("Practice more, improve fluency")

        return {
            "total_score": avg,
            "rating_text": self._to_rating(avg),
            "dimension_scores": {},
            "highlights": highlights,
            "improvements": improvements or ["Keep practicing"],
            "suggestions": all_suggestions[:5]
            or ["Practice product introductions and objection handling"],
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
            return "Excellent"
        elif score >= 80:
            return "Good"
        elif score >= 70:
            return "Satisfactory"
        elif score >= 60:
            return "Needs Improvement"
        return "Poor"


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
