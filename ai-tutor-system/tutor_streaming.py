"""
AI话术陪练系统 — SSE 流式管线编排器
编排 RAG检索 → AI流式生成 → 异步评估 的完整事件序列。
"""
import asyncio
import logging
from typing import List, Dict, AsyncGenerator

from tutor_models import SSEEvent
from tutor_services import (
    RAGService,
    AIService,
    get_rag_service,
    get_ai_service,
)

logger = logging.getLogger(__name__)


class StreamingPipeline:
    """Orchestrates the SSE event sequence for one chat round."""

    def __init__(
        self,
        rag_service: RAGService = None,
        ai_service: AIService = None,
    ):
        self.rag = rag_service or get_rag_service()
        self.ai = ai_service or get_ai_service()

    async def run(
        self,
        session_data: dict,
        user_message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute one full streaming chat round, yielding SSE event strings.

        Args:
            session_data: Session data dict (modified in-place with new messages)
            user_message: User's message content
        """
        scenario = session_data["scenario"]
        product = session_data.get("product", "")
        database = session_data.get("database") or self.rag.resolve_database(product)
        round_num = session_data["round"] + 1

        # ——— Stage 1: RAG Search ———
        yield SSEEvent.status("rag_searching", "Searching knowledge base...")

        product_knowledge, sales_knowledge, objection_knowledge = await asyncio.gather(
            asyncio.to_thread(
                self.rag.search, f"{product} 产品介绍 功能 价格", database, 3
            ),
            asyncio.to_thread(
                self.rag.search,
                f"{scenario.get('name', '')} 应对话术 销售技巧",
                database,
                3,
            ),
            asyncio.to_thread(
                self.rag.search, "常见异议处理 价格异议 技术异议", database, 2
            ),
        )

        knowledge_context = _build_knowledge_context(
            product_knowledge, sales_knowledge, objection_knowledge
        )
        total_kg = (
            len(product_knowledge) + len(sales_knowledge) + len(objection_knowledge)
        )
        logger.info(
            "Knowledge base: product=%d + sales=%d + objection=%d = %d total",
            len(product_knowledge),
            len(sales_knowledge),
            len(objection_knowledge),
            total_kg,
        )

        yield SSEEvent.status(
            "rag_complete",
            f"Found {total_kg} knowledge items",
            extra={
                "product_knowledge": len(product_knowledge),
                "sales_knowledge": len(sales_knowledge),
                "objection_knowledge": len(objection_knowledge),
            },
        )

        # ——— Stage 2: AI Streaming Generation ———
        yield SSEEvent.status("ai_generating", "Customer is typing...")

        conversation_history = []
        for msg in session_data["messages"][-5:]:
            role = "assistant" if msg["role"] == "ai" else "user"
            conversation_history.append({"role": role, "content": msg["content"]})

        system_prompt = _build_system_prompt(
            scenario=scenario,
            client_unit=session_data.get("client_unit", ""),
            product=product,
            scenario_type=session_data.get("scenario_type", ""),
            round_num=round_num,
            knowledge_context=knowledge_context,
        )

        full_response = ""
        try:
            for token in self.ai.generate_response_stream(
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                user_message=user_message,
            ):
                full_response += token
                yield SSEEvent.token(token)
        except Exception as e:
            logger.error("AI streaming interrupted: %s", e)
            yield SSEEvent.error("AI generation interrupted, please retry", "ai_stream_error")

        # ——— Stage 3: Release input (non-blocking for evaluation) ———
        yield SSEEvent.done(
            round_num,
            extra={"knowledge_count": total_kg},
        )

        # Save messages to session
        session_data["round"] = round_num
        session_data["messages"].append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": _now_iso(),
            }
        )
        session_data["messages"].append(
            {
                "role": "ai",
                "content": full_response,
                "timestamp": _now_iso(),
            }
        )

        # ——— Stage 4: Async Evaluation (does not block done) ———
        try:
            evaluation = await asyncio.to_thread(
                self.ai.evaluate,
                user_message=user_message,
                ai_response=full_response,
                round_num=round_num,
                scenario=scenario,
                knowledge_context=knowledge_context,
                database=database,
            )
            session_data["evaluations"].append(evaluation)
            yield SSEEvent.evaluation(evaluation)
        except asyncio.CancelledError:
            logger.info("Evaluation cancelled (user started next round), round=%d", round_num)
        except Exception as e:
            logger.error("Evaluation failed: %s", e)


def _build_knowledge_context(
    product_knowledge: List[Dict],
    sales_knowledge: List[Dict],
    objection_knowledge: List[Dict],
) -> str:
    """Build knowledge base context string for prompt injection."""
    parts = ["\n\n[IMPORTANT: Knowledge Base Info (must use, cannot fabricate)]\n"]

    if product_knowledge:
        parts.append("\nProduct Info (from KB):\n")
        for item in product_knowledge:
            parts.append(f"- {item['text']}\n")
    else:
        parts.append("\nNo product info in KB, use generic language\n")

    if sales_knowledge:
        parts.append("\nSales Scripts (from KB):\n")
        for item in sales_knowledge:
            parts.append(f"- {item['text']}\n")

    if objection_knowledge:
        parts.append("\nObjection Handling (from KB):\n")
        for item in objection_knowledge:
            parts.append(f"- {item['text']}\n")

    return "".join(parts)


def _build_system_prompt(
    scenario: dict,
    client_unit: str,
    product: str,
    scenario_type: str,
    round_num: int,
    knowledge_context: str,
) -> str:
    """Build the AI role-playing system prompt."""
    role_requirements = f"""
[Deep Role Requirements]
You are now fully immersed in the role of [{scenario['ai_role']}]:

1. Language style must match {scenario['ai_role']}'s identity
2. Behavior must reflect {scenario['name']}'s characteristics
3. Communication strategy must follow the scenario design
4. Natural questioning: weave KB questions into natural conversation, don't interrogate like a researcher
"""

    return f"""You are a professional sales trainer, now playing the role of [{scenario['ai_role']}] in a realistic business conversation with a sales representative.

{role_requirements}

[CORE PRINCIPLES (must strictly follow)]
1. Only use content from the "Knowledge Base Info" below to mention products and features
2. Absolutely do NOT fabricate product features, prices, or capabilities not in the KB
3. If KB has no relevant info, express confusion naturally: "I'm not sure about that", "Can you elaborate?"

[Conversation Scene]
- Client Unit: {client_unit}
- Product of Interest: {product}
- Context: {scenario_type}
- Round: {round_num}

[Knowledge Base Info (base your customer questions on this)]
{knowledge_context}

[Conversation Requirements]
1. Round {round_num}: you should {'ask deeper questions' if round_num > 1 else 'learn about the product'}
2. Questions should be natural, in the customer's voice — not like an interviewer
3. Start with phrases like: "We're quite focused on...", "I'd like to understand...", "Could you tell me about..."
4. Weave in natural reactions: "I see", "Hmm, interesting", "Oh, okay..."
5. Maintain the character's emotions and attitude — be a real customer, not a robot!

Now speak as {scenario['ai_role']} with natural, authentic customer language."""


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
