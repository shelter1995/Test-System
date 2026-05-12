# Phase 1: 后端拆分 + SSE 流式管线 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 tutor_backend.py (1155行) 拆分为 models/services/streaming 三层，新增 SSE 流式端点 /chat/stream，在保持现有 /chat 兼容的前提下让 AI 回复实时推送到前端。

**Architecture:** 三层拆分 — `tutor_models.py` 存放 Pydantic 模型和 SSE 事件类型，`tutor_services.py` 存放无状态业务逻辑（RAG检索、AI调用、会话管理、报告生成），`tutor_streaming.py` 编排 SSE 事件序列。所有服务通过依赖注入方式被路由使用，可独立测试。

**Tech Stack:** Python 3.11+, FastAPI + StreamingResponse, MiniMax API (stream: true), requests (SSE parsing), Pydantic v2

**Key design constraint:** 现有 /chat 端点行为不变，新 /chat/stream 端点并运行。前端可逐步迁移。

---

### File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `ai-tutor-system/tutor_models.py` | 新建 | Pydantic 数据模型 + SSE 事件类型 |
| `ai-tutor-system/tutor_services.py` | 新建 | RAGService / AIService / SessionManager / ReportGenerator |
| `ai-tutor-system/tutor_streaming.py` | 新建 | StreamingPipeline + SSE 事件编排器 |
| `ai-tutor-system/minimax_client.py` | 修改 | 新增 stream_chat_completion() |
| `ai-tutor-system/tutor_backend.py` | 重构 | 精简为 100 行路由 + 启动逻辑 |

---

### Task 1: 新建 tutor_models.py — 数据模型 + SSE 事件类型

**Files:**
- Create: `ai-tutor-system/tutor_models.py`

- [ ] **Step 1: 创建 tutor_models.py**

从 `tutor_backend.py` 迁移 Pydantic 模型，新增 SSE 事件类型。

```python
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
```

- [ ] **Step 2: 验证模型能正常导入**

```bash
cd ai-tutor-system && python -c "from tutor_models import SSEEvent, SessionStart; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 从 tutor_backend.py 删除已迁移的模型定义**

删除 `tutor_backend.py` 第 71-99 行的 `ScenarioCreate`, `SessionStart`, `ChatMessage`, `SessionEnd` 类定义，替换为导入：

```python
from tutor_models import ScenarioCreate, SessionStart, ChatMessage, SessionEnd
```

- [ ] **Step 4: 验证 tutor_backend.py 可导入**

```bash
cd ai-tutor-system && python -c "from tutor_backend import app; print('OK')"
```

Expected: `OK`（可能输出日志，但不应报错）

- [ ] **Step 5: 运行 generation API 测试确认无回归**

```bash
cd ai-tutor-system && python -m pytest tests/ -v
```

Expected: 15 passed

- [ ] **Step 6: Commit**

```bash
git add ai-tutor-system/tutor_models.py ai-tutor-system/tutor_backend.py
git commit -m "refactor: extract Pydantic models to tutor_models.py"
```

---

### Task 2: MiniMax 流式调用 — 新增 stream_chat_completion()

**Files:**
- Modify: `ai-tutor-system/minimax_client.py`

- [ ] **Step 1: 新增 stream_chat_completion() 方法**

在 `MiniMaxClient` 类中添加流式方法：

```python
def stream_chat_completion(
    self,
    messages: List[Dict[str, str]],
    temperature: float = 0.8,
    max_tokens: int = 800
):
    """
    调用 MiniMax 流式聊天完成接口

    Yields:
        str: AI 生成的文本增量（delta）

    用法:
        async for token in client.stream_chat_completion(messages):
            print(token, end="")
    """
    import json as json_lib

    url = f"{self.base_url}/text/chatcompletion_v2"
    headers = {
        "Authorization": f"Bearer {self.api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": self.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=self.timeout,
        stream=True
    )
    response.raise_for_status()

    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue

        chunk = line[6:]  # 去掉 "data: " 前缀
        if chunk == "[DONE]":
            break

        try:
            obj = json_lib.loads(chunk)
        except json_lib.JSONDecodeError:
            logger.warning(f"MiniMax 流式解析失败: {chunk[:100]}")
            continue

        # 检查业务错误
        base_resp = obj.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            err_msg = f"MiniMax 流式业务错误 [{base_resp.get('status_code')}]: {base_resp.get('status_msg', '')}"
            logger.error(err_msg)
            break

        choices = obj.get("choices", [])
        if not choices:
            continue

        delta = choices[0].get("delta", {})
        content = delta.get("content", "")
        if content:
            yield content
```

- [ ] **Step 2: 验证未破坏现有接口**

```bash
cd ai-tutor-system && python -c "from minimax_client import MiniMaxClient; c = MiniMaxClient('test', 'MiniMax-M2.7'); print(hasattr(c, 'stream_chat_completion'))"
```

Expected: `True`

- [ ] **Step 3: 运行 generation API 测试**

```bash
cd ai-tutor-system && python -m pytest tests/ -v
```

Expected: 15 passed

- [ ] **Step 4: Commit**

```bash
git add ai-tutor-system/minimax_client.py
git commit -m "feat: add stream_chat_completion to MiniMaxClient"
```

---

### Task 3: 新建 tutor_services.py — 业务逻辑层

**Files:**
- Create: `ai-tutor-system/tutor_services.py`

- [ ] **Step 1: 创建 tutor_services.py**

从 `tutor_backend.py` 提取所有业务逻辑函数，重构为无状态服务类。

```python
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
    """知识库检索服务，封装 RAG-Anything API 交互。"""

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
        """根据产品名解析知识库名称。未命中时回退到默认知识库。"""
        key = str(product or "").strip()
        if key in self.PRODUCT_TO_DATABASE:
            return self.PRODUCT_TO_DATABASE[key]
        default_db = str(getattr(config, "DEFAULT_RAG_DATABASE", "") or "").strip()
        return default_db or None

    def search(
        self, query: str, database: str = None, top_k: int = None
    ) -> List[Dict]:
        """
        从 RAG 知识库检索相关信息。
        返回: [{"text": "...", ...}, ...]
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

            # context 端点不存在时回退到 ai_enhanced_search
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
                    f"RAG 检索: '{query}' -> 数据库: {database or '默认'} -> {len(results)} 条"
                )
                return results
            else:
                logger.warning(f"RAG 检索失败: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"RAG 检索错误: {e}")
            return []


# ==================== AIService ====================

class AIService:
    """AI 生成服务，封装 MiniMax 流式和非流式调用。"""

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
        return bool(config.MINIMAX_API_KEY and
                   config.MINIMAX_API_KEY != "your_minimax_api_key_here")

    def generate_response(
        self,
        system_prompt: str,
        conversation_history: List[Dict],
        user_message: str,
    ) -> str:
        """非流式生成 AI 回复（向后兼容 /chat 端点）。"""
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
                logger.info(f"AI 生成回复: {content[:100]}...")
                return content
            else:
                logger.error(f"AI 生成失败: {result.get('error', '')}")
                return "抱歉，AI服务暂时不可用。"
        except Exception as e:
            logger.error(f"AI 生成异常: {e}")
            return f"抱歉，AI服务暂时不可用。"

    def generate_response_stream(
        self,
        system_prompt: str,
        conversation_history: List[Dict],
        user_message: str,
    ):
        """流式生成 AI 回复（用于 /chat/stream 端点）。

        Yields:
            str: token delta
        """
        if not self.available:
            yield "抱歉，AI服务未配置。"
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
            logger.error(f"AI 流式生成异常: {e}")
            yield "\n\n[AI回复中断，请重试]"

    def evaluate(
        self,
        user_message: str,
        ai_response: str,
        round_num: int,
        scenario: dict,
        knowledge_context: str,
        database: str = None,
    ) -> Dict[str, Any]:
        """评估用户话术，返回评分 + 建议。"""
        if not self.available:
            return {
                "overall_score": 70,
                "dimension_scores": {},
                "feedback": "AI服务未配置",
                "suggestions": [],
            }

        # 检索评估标准
        eval_knowledge = RAGService().search(
            f"销售话术评估标准 {scenario.get('name', '')}",
            top_k=3,
            database=database,
        )

        kb_info = ""
        if eval_knowledge:
            kb_info = "\n\n知识库中的评估标准参考：\n" + "\n".join([
                f"- {item['text']}" for item in eval_knowledge
            ])

        prompt = f"""你是一位专业的销售培训师，现在需要评估销售代表的话术。

【重要原则】
1. 评估必须基于知识库中的销售方法论和评估标准
2. 如果知识库中没有相关标准，基于行业最佳实践评估
3. 评估要客观、具体、有建设性

【对话上下文】
- 轮次：第{round_num}轮
- 场景：{scenario.get('name', '')}
- AI角色：{scenario.get('ai_role', '')}
- 销售代表说：{user_message}
- AI客户回应：{ai_response}
{kb_info}

请以JSON格式返回评估结果：
{{
    "overall_score": <总体评分0-100>,
    "dimension_scores": {{
        "开场话术": {{"score": <分数>, "feedback": "<反馈>"}},
        "需求挖掘": {{"score": <分数>, "feedback": "<反馈>"}},
        "产品介绍": {{"score": <分数>, "feedback": "<反馈>"}},
        "异议处理": {{"score": <分数>, "feedback": "<反馈>"}},
        "促成技巧": {{"score": <分数>, "feedback": "<反馈>"}}
    }},
    "feedback": "<整体反馈>",
    "suggestions": ["<建议1>", "<建议2>", "<建议3>"]
}}

只返回JSON，不要其他内容。"""

        try:
            result = self._client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )
            if not result["success"]:
                return self._fallback_evaluation()

            text = result["content"]
            # 提取 JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if not text.startswith("{"):
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1:
                    text = text[start:end + 1]

            evaluation = json.loads(text)
            logger.info(f"AI 评估完成: 总分 {evaluation.get('overall_score', 0)}")
            return evaluation
        except Exception as e:
            logger.error(f"AI 评估异常: {e}")
            return self._fallback_evaluation()

    def _fallback_evaluation(self) -> dict:
        return {
            "overall_score": 70,
            "dimension_scores": {},
            "feedback": "评估服务暂时不可用",
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
        """生成 AI 开场白。"""
        if not self.available:
            return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"

        rag = RAGService()
        product_knowledge = rag.search(f"{product} 产品介绍", top_k=3, database=database)
        opening_knowledge = rag.search(
            f"{scenario.get('name', '')} 开场话术 初次沟通",
            top_k=3,
            database=database,
        )

        knowledge_context = ""
        if product_knowledge or opening_knowledge:
            knowledge_context = "\n\n【知识库相关信息】\n"
            if product_knowledge:
                knowledge_context += "\n产品信息：\n" + "\n".join([
                    f"- {item['text']}" for item in product_knowledge
                ])
            if opening_knowledge:
                knowledge_context += "\n开场话术参考：\n" + "\n".join([
                    f"- {item['text']}" for item in opening_knowledge
                ])

        prompt = f"""你现在完全沉浸在【{scenario['ai_role']}】这个角色中，作为{client_unit}的真实客户与销售代表进行初次沟通。

【角色深度设定】
你现在就是{scenario['ai_role']}，而不是扮演这个角色：
- 你有自己的工作需求、压力和关注点
- 你有自己的沟通风格和专业背景
- 你对{product}有真实的兴趣或疑问

【角色特征】
- 你的性格特点：{', '.join(scenario.get('customer_traits', ['专业、谨慎']))}
- 你的行为倾向：{', '.join(scenario.get('ai_strategy', ['了解产品信息']))}

【重要原则】
1. 你只能使用知识库中提供的产品信息来提及产品
2. 不能编造产品功能、价格或特性
3. 开场白要真实、自然，就像真实的{scenario['ai_role']}在说话
4. 体现真实的需求或疑问，不要像在背台词

【场景信息】
- 你所在单位：{client_unit}
- 你想了解的产品：{product}
- 沟通场景：{scenario_type}
{knowledge_context}

请你作为{scenario['ai_role']}，用真实自然的语言说出开场白。
直接说出开场白，不要有任何解释或说明。"""

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
    """会话管理服务。"""

    @staticmethod
    def generate_id() -> str:
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    @staticmethod
    def save(session_id: str, session_data: dict) -> None:
        try:
            session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            logger.info(f"会话已保存: {session_id}")
        except Exception as e:
            logger.error(f"保存会话失败: {e}")

    @staticmethod
    def load(session_id: str) -> Optional[dict]:
        try:
            session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
            if session_file.exists():
                with open(session_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载会话失败: {e}")
        return None

    @staticmethod
    def list_all() -> List[dict]:
        """列出所有历史会话。"""
        sessions_dir = Path(config.SESSIONS_DIR)
        history = []
        for session_file in sessions_dir.glob("*.json"):
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            report = session_data.get("report", {})
            history.append({
                "session_id": session_data["session_id"],
                "scenario": session_data["scenario"]["name"],
                "rounds": session_data["round"],
                "status": session_data["status"],
                "created_at": session_data["created_at"],
                "client_unit": session_data.get("client_unit", ""),
                "product": session_data.get("product", ""),
                "score": report.get("total_score"),
                "rating": report.get("rating_text"),
            })
        history.sort(key=lambda x: x["created_at"], reverse=True)
        return history


# ==================== ReportGenerator ====================

class ReportGenerator:
    """报告生成服务。"""

    def __init__(self, ai_service: AIService = None):
        self._ai = ai_service or AIService()

    def generate(self, session_data: dict) -> dict:
        """调用 AI 生成最终评估报告。"""
        if not self._ai.available:
            return self._fallback(session_data)

        messages = session_data.get("messages", [])
        scenario = session_data.get("scenario", {})
        rounds = session_data.get("round", 0)
        product = session_data.get("product", "")
        database = session_data.get("database") or RAGService().resolve_database(product)

        training_standards = RAGService().search(
            "销售培训标准 评估方法 销售方法论",
            top_k=5,
            database=database,
        )

        kb_ctx = ""
        if training_standards:
            kb_ctx = "\n\n【知识库中的培训标准】\n" + "\n".join([
                f"- {item['text']}" for item in training_standards
            ])
        else:
            kb_ctx = "\n\n【注意】当前知识库中没有销售培训标准，请基于行业最佳实践评估。"

        # 构建对话摘要
        conv_summary = ""
        for i, msg in enumerate(messages[-10:]):
            role = "客户" if msg.get("role") == "ai" else "销售代表"
            conv_summary += f"\n{role}: {msg.get('content', '')}\n"

        prompt = f"""你是一位资深的销售培训专家，现在要对一场销售陪练对话进行总结评估。

【重要原则】
1. 评估标准必须来自知识库中的销售培训方法论
2. 不能编造不存在的评估方法
3. 如果知识库中没有相关标准，明确说明

【对话信息】
- 场景：{scenario.get('name', '')}
- 轮次：{rounds}
- 客户单位：{session_data.get('client_unit', '')}
- 产品：{session_data.get('product', '')}

【对话摘要】
{conv_summary}
{kb_ctx}

请以JSON格式返回评估报告：
{{
    "total_score": <总分0-100>,
    "rating_text": "<评级：优秀/良好/满意/待改进/较差>",
    "dimension_scores": {{}},
    "highlights": ["<亮点1>", "<亮点2>", "<亮点3>"],
    "improvements": ["<待改进1>", "<待改进2>", "<待改进3>"],
    "suggestions": ["<建议1>", "<建议2>", "<建议3>"]
}}

只返回JSON，不要其他内容。"""

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
                    text = text[start:end + 1]

            report = json.loads(text)
            report.setdefault("total_score", self._calc_avg(session_data))
            report.setdefault("rating_text", self._to_rating(report["total_score"]))
            for field in ["highlights", "improvements", "suggestions"]:
                report.setdefault(field, [])
            return report
        except Exception as e:
            logger.error(f"生成报告异常: {e}")
            return self._fallback(session_data)

    def _fallback(self, session_data: dict) -> dict:
        """兜底报告（AI 不可用时）。"""
        evals = session_data.get("evaluations", [])
        avg = self._calc_avg(session_data)
        rounds = session_data.get("round", 0)

        all_suggestions = []
        for ev in evals:
            for s in ev.get("suggestions", []):
                if s and s not in all_suggestions:
                    all_suggestions.append(s)

        highlights = [f"完成{rounds}轮对话练习"]
        improvements = []
        if avg >= 80:
            highlights.append("表现良好")
        elif avg < 60:
            improvements.append("建议增加练习，提升话术熟练度")

        return {
            "total_score": avg,
            "rating_text": self._to_rating(avg),
            "dimension_scores": {},
            "highlights": highlights,
            "improvements": improvements or ["继续保持练习"],
            "suggestions": all_suggestions[:5] or ["建议多练习产品介绍和异议处理话术"],
        }

    @staticmethod
    def _calc_avg(session_data: dict) -> int:
        evals = session_data.get("evaluations", [])
        if evals:
            scores = [e.get("overall_score", 0) for e in evals if e.get("overall_score", 0) > 0]
            return round(sum(scores) / len(scores)) if scores else 70
        return 70

    @staticmethod
    def _to_rating(score: int) -> str:
        if score >= 90: return "优秀"
        elif score >= 80: return "良好"
        elif score >= 70: return "满意"
        elif score >= 60: return "待改进"
        return "较差"


# ==================== 单例（可选） ====================

_default_rag = None
_default_ai = None


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
```

- [ ] **Step 2: 验证 tutor_services.py 能导入（可能缺少依赖时跳过 MiniMax 初始化）**

```bash
cd ai-tutor-system && python -c "from tutor_services import RAGService, SessionManager, ReportGenerator; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ai-tutor-system/tutor_services.py
git commit -m "feat: extract business logic to tutor_services.py"
```

---

### Task 4: 新建 tutor_streaming.py — SSE 管线编排

**Files:**
- Create: `ai-tutor-system/tutor_streaming.py`

- [ ] **Step 1: 创建 tutor_streaming.py**

```python
"""
AI话术陪练系统 — SSE 流式管线编排器
编排 RAG检索 → AI流式生成 → 异步评估 的完整事件序列。
"""
import asyncio
import logging
from typing import List, Dict, Optional, AsyncGenerator

from tutor_models import SSEEvent
from tutor_services import (
    RAGService,
    AIService,
    get_rag_service,
    get_ai_service,
)

logger = logging.getLogger(__name__)


class StreamingPipeline:
    """编排一轮对话的 SSE 事件流。"""

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
        执行一轮完整的流式对话，yield SSE 事件字符串。

        Args:
            session_data: 会话数据字典（会被原地修改）
            user_message: 用户发送的消息内容
        """
        scenario = session_data["scenario"]
        product = session_data.get("product", "")
        database = session_data.get("database") or self.rag.resolve_database(product)
        round_num = session_data["round"] + 1  # 本轮的轮次

        # ——— 阶段 1: RAG 检索 ———
        yield SSEEvent.status("rag_searching", "检索知识库中...")

        product_knowledge, sales_knowledge, objection_knowledge = await asyncio.gather(
            asyncio.to_thread(self.rag.search, f"{product} 产品介绍 功能 价格", database, 3),
            asyncio.to_thread(self.rag.search, f"{scenario.get('name', '')} 应对话术 销售技巧", database, 3),
            asyncio.to_thread(self.rag.search, "常见异议处理 价格异议 技术异议", database, 2),
        )

        knowledge_context = _build_knowledge_context(
            product_knowledge, sales_knowledge, objection_knowledge
        )
        total_kg = len(product_knowledge) + len(sales_knowledge) + len(objection_knowledge)
        logger.info(
            f"知识库检索: 产品 {len(product_knowledge)} + 话术 {len(sales_knowledge)} "
            f"+ 异议 {len(objection_knowledge)} = {total_kg} 条"
        )

        yield SSEEvent.status(
            "rag_complete",
            f"检索到 {total_kg} 条知识",
            extra={
                "product_knowledge": len(product_knowledge),
                "sales_knowledge": len(sales_knowledge),
                "objection_knowledge": len(objection_knowledge),
            },
        )

        # ——— 阶段 2: AI 流式生成 ———
        yield SSEEvent.status("ai_generating", "客户正在输入...")

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
            logger.error(f"AI 流式生成中断: {e}")
            yield SSEEvent.error("AI 生成中断，请重试", "ai_stream_error")

        # ——— 阶段 3: 释放输入框 ———
        yield SSEEvent.done(
            round_num,
            extra={
                "knowledge_count": total_kg,
            },
        )

        # 保存本轮消息到 session_data
        session_data["round"] = round_num
        session_data["messages"].append({
            "role": "user",
            "content": user_message,
            "timestamp": _now_iso(),
        })
        session_data["messages"].append({
            "role": "ai",
            "content": full_response,
            "timestamp": _now_iso(),
        })

        # ——— 阶段 4: 异步评估（不阻塞 done） ———
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
            logger.info(f"评估被取消（用户开始下一轮），round={round_num}")
        except Exception as e:
            logger.error(f"评估失败: {e}")


def _build_knowledge_context(
    product_knowledge: List[Dict],
    sales_knowledge: List[Dict],
    objection_knowledge: List[Dict],
) -> str:
    """构建注入 prompt 的知识库上下文。"""
    parts = ["\n\n【重要：知识库信息（必须使用这些信息，不能编造）】\n"]

    if product_knowledge:
        parts.append("\n产品信息（来自知识库）：\n")
        for item in product_knowledge:
            parts.append(f"- {item['text']}\n")
    else:
        parts.append("\n知识库中没有产品信息，请使用通用话术\n")

    if sales_knowledge:
        parts.append("\n应对话术（来自知识库）：\n")
        for item in sales_knowledge:
            parts.append(f"- {item['text']}\n")

    if objection_knowledge:
        parts.append("\n异议处理方法（来自知识库）：\n")
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
    """构建 AI 角色扮演的系统 prompt。"""
    role_requirements = f"""
【角色深度要求】
你现在完全沉浸在【{scenario['ai_role']}】这个角色中：

1. 语言风格必须符合{scenario['ai_role']}的身份
2. 行为特征必须展现{scenario['name']}的特点
3. 沟通策略必须符合场景设计
4. 自然提问要求：将知识库中的问题融入真实对话中，不要像查资料一样直接问
"""

    return f"""你是一位专业的销售培训师，现在扮演【{scenario['ai_role']}】与销售代表进行真实的商务对话。

{role_requirements}

【核心原则（必须严格遵守）】
1. 你只能使用下面"知识库信息"中的内容来提及产品和功能
2. 绝对不能编造知识库中没有的产品功能、价格或特性
3. 如果知识库中没有相关信息，用客户的方式表达疑虑

【对话场景】
- 客户单位：{client_unit}
- 感兴趣的产品：{product}
- 沟通场景：{scenario_type}
- 对话轮次：第{round_num}轮

【知识库信息（你可以基于这些内容提出客户疑问）】
{knowledge_context}

【对话要求】
1. 第{round_num}轮对话，你应该{'深入提问' if round_num > 1 else '初步了解产品'}
2. 提问要自然，用客户的语言表达，不要像面试官或考官
3. 保持角色的情绪和态度，展现真实客户的状态

现在请作为{scenario['ai_role']}，用自然的客户语言回复销售代表。记住：你是真实的客户，不是机器人！"""


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
```

- [ ] **Step 2: 验证 tutor_streaming.py 可导入**

```bash
cd ai-tutor-system && python -c "from tutor_streaming import StreamingPipeline; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ai-tutor-system/tutor_streaming.py
git commit -m "feat: add SSE streaming pipeline for tutor chat"
```

---

### Task 5: 重构 tutor_backend.py — 精简 + 新增 /chat/stream

**Files:**
- Modify: `ai-tutor-system/tutor_backend.py`

- [ ] **Step 1: 重写 tutor_backend.py**

替换为精简版本，保留所有现有端点，新增 `/chat/stream`。

```python
"""
AI话术陪练系统 - 后端服务（精简版）
路由层 — 业务逻辑已迁移至 tutor_services.py 和 tutor_streaming.py
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from datetime import datetime
import json
import logging

import tutor_config as config
from tutor_models import ScenarioCreate, SessionStart, ChatMessage, SessionEnd
from tutor_services import (
    AIService,
    SessionManager,
    ReportGenerator,
    get_rag_service,
    get_ai_service,
)
from tutor_streaming import StreamingPipeline

# 日志
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="AI话术陪练系统",
    description="基于MiniMax AI和RAG知识库的智能角色扮演训练系统",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 挂载内容生成路由
from generation_api import router as generation_router
app.include_router(generation_router)

# ==================== 全局状态 ====================

sessions = {}  # 内存中的活跃会话缓存
scenarios = config.DEFAULT_SCENARIOS.copy()

# 服务实例
ai_service = get_ai_service()
rag_service = get_rag_service()
report_gen = ReportGenerator(ai_service)
streaming_pipeline = StreamingPipeline(rag_service, ai_service)

# 日志 AI 状态
if ai_service.available:
    logger.info(f"MiniMax AI 已配置，模型: {config.MINIMAX_MODEL}")
else:
    logger.warning("MiniMax AI API Key 未配置")


# ==================== API 端点 ====================

@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"error": "前端页面未找到"}


@app.get("/api/status")
async def api_status():
    return {
        "status": "running",
        "message": "AI话术陪练系统正在运行",
        "ai_configured": ai_service.available,
        "ai_provider": "MiniMax" if ai_service.available else "未配置",
        "ai_model": config.MINIMAX_MODEL if ai_service.available else None,
        "rag_service": config.RAG_SERVICE_URL,
    }


@app.get("/scenarios")
async def get_scenarios():
    return {
        "preset": scenarios,
        "custom_count": len([s for s in scenarios.values() if s.get("is_custom")]),
    }


@app.post("/scenarios/create")
async def create_scenario(scenario: ScenarioCreate):
    scenario_id = f"custom_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    new_scenario = {
        "id": scenario_id,
        "name": scenario.name,
        "ai_role": scenario.ai_role,
        "user_role": scenario.user_role,
        "description": scenario.description,
        "customer_traits": scenario.customer_traits,
        "ai_strategy": scenario.ai_strategy,
        "success_criteria": scenario.success_criteria,
        "is_custom": True,
        "created_at": datetime.now().isoformat(),
    }
    scenarios[scenario_id] = new_scenario

    try:
        scenarios_file = Path(config.SCENARIOS_FILE)
        with open(scenarios_file, "w", encoding="utf-8") as f:
            json.dump(scenarios, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存场景失败: {e}")

    return {"message": "场景创建成功", "scenario_id": scenario_id, "scenario": new_scenario}


@app.post("/session/start")
async def start_session(session_start: SessionStart):
    if not ai_service.available:
        raise HTTPException(status_code=500, detail="AI服务未配置")

    scenario_id = session_start.scenario_id
    if scenario_id.startswith("custom_") and session_start.custom_scenario:
        custom = session_start.custom_scenario
        scenario = {
            "id": scenario_id,
            "name": custom.name,
            "ai_role": custom.ai_role,
            "user_role": custom.user_role,
            "description": custom.description,
            "customer_traits": custom.customer_traits,
            "ai_strategy": custom.ai_strategy,
            "success_criteria": custom.success_criteria,
        }
    else:
        if scenario_id not in scenarios:
            raise HTTPException(status_code=404, detail="场景不存在")
        scenario = scenarios[scenario_id]

    session_id = SessionManager.generate_id()
    session_data = {
        "session_id": session_id,
        "scenario": scenario,
        "client_unit": session_start.client_unit,
        "product": session_start.product,
        "scenario_type": session_start.scenario_type,
        "database": session_start.database,
        "round": 0,
        "messages": [],
        "evaluations": [],
        "created_at": datetime.now().isoformat(),
        "status": "active",
    }

    scenario_hint = f"""你是{session_start.client_unit}的{scenario['ai_role']}。

【背景信息】
- 单位：{session_start.client_unit}
- 产品：{session_start.product}
- 场景：{session_start.scenario_type}
- 你的特点：{', '.join(scenario.get('customer_traits', []))}

现在请销售经理开始对话..."""

    sessions[session_id] = session_data
    SessionManager.save(session_id, session_data)

    return {
        "session_id": session_id,
        "scenario": scenario,
        "opening_message": scenario_hint,
        "user_should_start": True,
        "session_info": {
            "client_unit": session_start.client_unit,
            "product": session_start.product,
            "scenario_type": session_start.scenario_type,
        },
    }


@app.post("/chat/stream")
async def chat_stream(chat_message: ChatMessage):
    """SSE 流式对话端点 — 新增。"""
    session_id = chat_message.session_id

    # 获取会话
    if session_id not in sessions:
        session_data = SessionManager.load(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        sessions[session_id] = session_data
    else:
        session_data = sessions[session_id]

    # 处理暂停（评估请求）
    if chat_message.is_pause:
        if session_data["messages"]:
            last_user = [m for m in session_data["messages"] if m["role"] == "user"][-1]
            last_ai = [m for m in session_data["messages"] if m["role"] == "ai"][-1]
            product = session_data.get("product", "")
            database = session_data.get("database") or rag_service.resolve_database(product)

            async def pause_eval_stream():
                import asyncio
                evaluation = await asyncio.to_thread(
                    ai_service.evaluate,
                    last_user["content"],
                    last_ai["content"],
                    session_data["round"],
                    session_data["scenario"],
                    "",
                    database=database,
                )
                from tutor_models import SSEEvent
                yield SSEEvent.evaluation(evaluation)

            return StreamingResponse(
                pause_eval_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    # 正常流式对话
    async def event_stream():
        async for event_str in streaming_pipeline.run(session_data, chat_message.message):
            yield event_str
        SessionManager.save(session_id, session_data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat")
async def chat(chat_message: ChatMessage):
    """传统非流式对话端点 — 保持向后兼容。"""
    import asyncio as aio

    session_id = chat_message.session_id

    if session_id not in sessions:
        session_data = SessionManager.load(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        sessions[session_id] = session_data
    else:
        session_data = sessions[session_id]

    # 暂停获取反馈
    if chat_message.is_pause:
        if session_data["messages"]:
            last_user = [m for m in session_data["messages"] if m["role"] == "user"][-1]
            last_ai = [m for m in session_data["messages"] if m["role"] == "ai"][-1]
            product = session_data.get("product", "")
            database = session_data.get("database") or rag_service.resolve_database(product)

            evaluation = await aio.to_thread(
                ai_service.evaluate,
                last_user["content"],
                last_ai["content"],
                session_data["round"],
                session_data["scenario"],
                "",
                database=database,
            )
            return {"is_pause_response": True, "evaluation": evaluation, "ai_response": None}

    # 保存用户消息
    session_data["messages"].append({
        "role": "user",
        "content": chat_message.message,
        "timestamp": datetime.now().isoformat(),
    })
    session_data["round"] += 1

    product = session_data.get("product", "")
    database = session_data.get("database") or rag_service.resolve_database(product)

    # RAG 检索
    product_knowledge, sales_knowledge, objection_knowledge = await aio.gather(
        aio.to_thread(rag_service.search, f"{product} 产品介绍 功能 价格", database, 3),
        aio.to_thread(rag_service.search, f"{session_data['scenario'].get('name', '')} 应对话术 销售技巧", database, 3),
        aio.to_thread(rag_service.search, "常见异议处理 价格异议 技术异议", database, 2),
    )

    # 构建知识库上下文
    from tutor_streaming import _build_knowledge_context, _build_system_prompt
    knowledge_context = _build_knowledge_context(product_knowledge, sales_knowledge, objection_knowledge)

    # 构建对话历史
    conversation_history = []
    for msg in session_data["messages"][-5:]:
        role = "assistant" if msg["role"] == "ai" else "user"
        conversation_history.append({"role": role, "content": msg["content"]})

    # AI 生成
    system_prompt = _build_system_prompt(
        scenario=session_data["scenario"],
        client_unit=session_data.get("client_unit", ""),
        product=product,
        scenario_type=session_data.get("scenario_type", ""),
        round_num=session_data["round"],
        knowledge_context=knowledge_context,
    )

    ai_response = await aio.to_thread(
        ai_service.generate_response,
        system_prompt,
        conversation_history,
        chat_message.message,
    )

    # AI 评估
    evaluation = await aio.to_thread(
        ai_service.evaluate,
        chat_message.message,
        ai_response,
        session_data["round"],
        session_data["scenario"],
        knowledge_context,
        database=database,
    )

    session_data["messages"].append({
        "role": "ai",
        "content": ai_response,
        "timestamp": datetime.now().isoformat(),
    })
    session_data["evaluations"].append(evaluation)
    SessionManager.save(session_id, session_data)

    return {
        "is_pause_response": False,
        "ai_response": ai_response,
        "evaluation": evaluation,
        "round": session_data["round"],
        "session_id": session_id,
        "debug_info": {
            "knowledge_found": len(product_knowledge) + len(sales_knowledge) + len(objection_knowledge),
            "product_knowledge": len(product_knowledge),
            "sales_knowledge": len(sales_knowledge),
            "objection_knowledge": len(objection_knowledge),
        },
    }


@app.post("/session/end")
async def end_session(session_end: SessionEnd):
    session_id = session_end.session_id

    if session_id in sessions:
        session_data = sessions[session_id]
    else:
        session_data = SessionManager.load(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")

    session_data["status"] = "completed"
    session_data["ended_at"] = datetime.now().isoformat()

    if session_end.detail_level == "simple":
        report = report_gen._fallback(session_data)
    else:
        report = report_gen.generate(session_data)

    report["session_id"] = session_id
    report["scenario"] = session_data["scenario"]["name"]
    report["rounds"] = session_data["round"]
    report["timestamp"] = datetime.now().isoformat()

    session_data["report"] = report
    SessionManager.save(session_id, session_data)

    if session_id in sessions:
        del sessions[session_id]

    return report


@app.get("/history")
async def get_history():
    return {"history": SessionManager.list_all()}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    session_data = SessionManager.load(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_data


# ==================== 启动 ====================

def check_port_available(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except socket.error:
            return False


if __name__ == "__main__":
    import uvicorn
    import sys

    print("=" * 60)
    print("  AI话术陪练系统 - RAG增强版 v2.1 (SSE 流式)")
    print("=" * 60)
    print()

    if not check_port_available(config.TUTOR_SERVICE_PORT):
        print(f"[ERROR] 端口 {config.TUTOR_SERVICE_PORT} 已被占用！")
        sys.exit(1)

    if ai_service.available:
        print("[OK] MiniMax AI 已配置")
        print(f"[OK] 使用模型：{config.MINIMAX_MODEL}")
        print("[OK] SSE 流式输出已启用")
    else:
        print("[!] MiniMax AI 未配置")

    print(f"[OK] RAG服务：{config.RAG_SERVICE_URL}")
    print()
    print(f"API地址: http://{config.TUTOR_SERVICE_HOST}:{config.TUTOR_SERVICE_PORT}")
    print(f"SSE端点: http://{config.TUTOR_SERVICE_HOST}:{config.TUTOR_SERVICE_PORT}/chat/stream")
    print()
    print("启动中...")

    uvicorn.run(
        app,
        host=config.TUTOR_SERVICE_HOST,
        port=config.TUTOR_SERVICE_PORT,
        log_level="info",
    )
```

- [ ] **Step 2: 验证应用能正常导入**

```bash
cd ai-tutor-system && python -c "from tutor_backend import app; print('App loaded OK')"
```

Expected: `App loaded OK`（可能输出 MiniMax 配置日志）

- [ ] **Step 3: 运行 generation API 测试**

```bash
cd ai-tutor-system && python -m pytest tests/ -v
```

Expected: 15 passed

- [ ] **Step 4: 测试 /api/status 端点**

启动服务后（或直接测试导入）：
```bash
cd ai-tutor-system && python -c "
from fastapi.testclient import TestClient
from tutor_backend import app
client = TestClient(app)
resp = client.get('/api/status')
print(resp.status_code, resp.json()['status'])
"
```

Expected: `200 running`

- [ ] **Step 5: Commit**

```bash
git add ai-tutor-system/tutor_backend.py
git commit -m "refactor: slim tutor_backend.py to routes, add /chat/stream SSE endpoint"
```

---

### Task 6: 端到端验证 + 处理 Session 生命周期

**Files:** 无新建

- [ ] **Step 1: 验证所有端点可访问**

```bash
cd ai-tutor-system && python -c "
from fastapi.testclient import TestClient
from tutor_backend import app
client = TestClient(app)

# 验证关键端点
print('GET /', client.get('/').status_code)
print('GET /api/status', client.get('/api/status').status_code)
print('GET /scenarios', client.get('/scenarios').status_code)
print('GET /history', client.get('/history').status_code)
print('All endpoints accessible')
"
```

Expected: 所有状态码 200

- [ ] **Step 2: 运行全量测试**

```bash
cd ai-tutor-system && python -m pytest tests/ -v
```

Expected: 15 passed

- [ ] **Step 3: 验证 SSE 事件格式**

```bash
cd ai-tutor-system && python -c "
from tutor_models import SSEEvent
import json

# 验证各事件类型格式
events = [
    SSEEvent.status('rag_searching', '检索中...'),
    SSEEvent.token('你好'),
    SSEEvent.done(3, extra={'knowledge_count': 7}),
    SSEEvent.evaluation({'overall_score': 82}),
    SSEEvent.error('测试错误', 'test_code'),
]
for e in events:
    assert e.startswith('event: ')
    assert 'data: ' in e
print(f'All {len(events)} event types validated')
"
```

Expected: `All 5 event types validated`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: add SSE event format validation, verify all endpoints"
```

---

## Post-Phase 1 Checklist

- [ ] `tutor_backend.py` 从 1155 行精简至约 250 行
- [ ] 新增 3 个模块文件：`tutor_models.py`, `tutor_services.py`, `tutor_streaming.py`
- [ ] `/chat` 端点保持不变（向后兼容）
- [ ] `/chat/stream` 端点返回标准 SSE 格式
- [ ] 15 个 generation API 测试通过
- [ ] `MiniMaxClient.stream_chat_completion()` 可用
- [ ] 所有服务类可独立导入和测试

## Phase 2 预览（不在本计划范围内）

- 修改 `app_with_health_check.js` 使用 EventSource 消费 `/chat/stream`
- 打字机效果渲染 + 阶段指示器
- 非阻塞评分（done 即释放输入框，AbortController 管理旧连接）
