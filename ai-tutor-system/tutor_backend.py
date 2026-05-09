"""
AI话术陪练系统 - 后端服务
基于MiniMax AI和RAG知识库的智能角色扮演训练系统

核心原则：
1. 所有对话必须经过AI生成，不能Python硬编码
2. 所有产品知识必须来自RAG知识库，不能编造
3. 评估反馈必须由AI基于知识库标准生成
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import asyncio
import logging
from pathlib import Path
import requests

# 导入配置
import tutor_config as config

# 导入MiniMax客户端
try:
    from minimax_client import MiniMaxClient
    minimax_available = True
except ImportError:
    minimax_available = False
    MiniMaxClient = None

# 配置日志
logging.basicConfig(
    level=config.LOG_LEVEL,
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# 初始化FastAPI应用
app = FastAPI(
    title="AI话术陪练系统",
    description="基于MiniMax AI和RAG知识库的智能角色扮演训练系统",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件（CSS、JS等）
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 挂载内容生成 API 路由
from generation_api import router as generation_router
app.include_router(generation_router)

# ==================== 数据模型 ====================

class ScenarioCreate(BaseModel):
    """创建自定义场景"""
    name: str
    ai_role: str
    user_role: str
    description: str
    customer_traits: List[str]
    ai_strategy: List[str]
    success_criteria: List[str]

class SessionStart(BaseModel):
    """开始会话"""
    scenario_id: str
    client_unit: Optional[str] = "某公司"
    product: Optional[str] = "商务视频彩铃"
    scenario_type: Optional[str] = "初次沟通"
    database: Optional[str] = None  # 用户显式选择的知识库
    custom_scenario: Optional[ScenarioCreate] = None

class ChatMessage(BaseModel):
    """发送消息"""
    session_id: str
    message: str
    is_pause: bool = False  # 是否暂停获取反馈

class SessionEnd(BaseModel):
    """结束会话"""
    session_id: str
    detail_level: str = "simple"

# ==================== 全局变量 ====================
sessions = {}  # 存储活跃会话
scenarios = config.DEFAULT_SCENARIOS.copy()  # 加载默认场景

# 产品名称到数据库的映射关系
PRODUCT_TO_DATABASE = {
    "商务视频彩铃": "商务彩铃",
    "视频彩铃": "商务彩铃",
    "商务彩铃": "商务彩铃",
    "量子": "quantum",
    "量子计算": "quantum"
}


def resolve_product_database(product: str | None) -> str | None:
    """根据产品名解析知识库。未命中时回退到默认知识库。"""
    key = str(product or "").strip()
    if key in PRODUCT_TO_DATABASE:
        return PRODUCT_TO_DATABASE[key]
    default_db = str(getattr(config, "DEFAULT_RAG_DATABASE", "") or "").strip()
    return default_db or None

# 检查MiniMax AI配置
if not config.MINIMAX_API_KEY or config.MINIMAX_API_KEY == "your_minimax_api_key_here":
    logger.warning("⚠️  MiniMax AI API Key未配置，请在tutor_config.py中设置MINIMAX_API_KEY")
    ai_client = None
else:
    try:
        if minimax_available:
            ai_client = MiniMaxClient(
                api_key=config.MINIMAX_API_KEY,
                model=config.MINIMAX_MODEL
            )
            logger.info(f"✅ MiniMax AI已配置，使用模型: {config.MINIMAX_MODEL}")
        else:
            logger.error("❌ MiniMax客户端模块未找到，请确保minimax_client.py存在")
            ai_client = None
    except Exception as e:
        logger.error(f"❌ MiniMax AI初始化失败: {e}")
        ai_client = None

# ==================== 辅助函数 ====================

def generate_session_id() -> str:
    """生成会话ID"""
    return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def save_session(session_id: str, session_data: dict):
    """保存会话记录"""
    try:
        session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 会话已保存: {session_id}")
    except Exception as e:
        logger.error(f"❌ 保存会话失败: {e}")

def load_session(session_id: str) -> Optional[dict]:
    """加载会话记录"""
    try:
        session_file = Path(config.SESSIONS_DIR) / f"{session_id}.json"
        if session_file.exists():
            with open(session_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"❌ 加载会话失败: {e}")
    return None

def search_rag_knowledge(query: str, top_k: int = config.RAG_TOP_K, database: str = None) -> List[Dict]:
    """
    从RAG知识库检索相关信息

    这是系统最核心的函数！
    所有产品知识、话术、案例都必须从这里获取
    """
    try:
        params = {"query": query, "n_results": top_k}
        if database:
            params["database"] = database

        endpoint = "context" if database else "ai_enhanced_search"
        response = requests.post(
            f"{config.RAG_SERVICE_URL}/{endpoint}",
            json=params,
            timeout=config.RAG_REQUEST_TIMEOUT
        )
        if response.status_code == 404 and endpoint == "context":
            response = requests.post(
                f"{config.RAG_SERVICE_URL}/ai_enhanced_search",
                json=params,
                timeout=config.RAG_REQUEST_TIMEOUT
            )

        if response.status_code == 200:
            data = response.json()
            results = data.get("contexts", data.get("results", []))
            logger.info(f"📚 RAG检索: '{query}' -> 数据库: {database or '默认'} -> 找到{len(results)}条结果")
            return results
        else:
            logger.warning(f"⚠️  RAG检索失败: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ RAG检索错误: {e}")
        return []

def call_ai_for_response(
    system_prompt: str,
    conversation_history: List[Dict],
    user_message: str
) -> str:
    """
    调用AI生成回复

    核心原则：
    1. AI必须基于提供的知识库信息生成回复
    2. 不能编造知识库以外的产品信息
    3. 如果知识库没有相关信息，明确说明
    """
    if not ai_client:
        return "抱歉，AI服务未配置。请在tutor_config.py中设置MINIMAX_API_KEY。"

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            *conversation_history,
            {"role": "user", "content": user_message}
        ]

        result = ai_client.chat_completion(
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )

        if result["success"]:
            ai_response = result["content"]
            logger.info(f"✅ AI生成回复: {ai_response[:100]}...")
            return ai_response
        else:
            logger.error(f"❌ AI生成回复失败: {result.get('error', 'Unknown error')}")
            return "抱歉，AI服务暂时不可用。"

    except Exception as e:
        logger.error(f"❌ AI生成回复失败: {e}")
        return f"抱歉，AI服务暂时不可用。"

def call_ai_for_evaluation(
    user_message: str,
    ai_response: str,
    round_num: int,
    scenario: dict,
    knowledge_context: str,
    database: str = None
) -> Dict[str, Any]:
    """
    调用AI进行话术评估

    核心原则：
    1. 评估必须由AI完成，不能Python硬编码
    2. 评估标准必须基于知识库中的销售方法论
    3. 不能编造评估标准
    """
    if not ai_client:
        return {
            "overall_score": 70,
            "dimension_scores": {},
            "feedback": "AI服务未配置",
            "suggestions": []
        }

    # 检索评估标准
    evaluation_knowledge = search_rag_knowledge(
        f"销售话术评估标准 {scenario.get('name', '')}",
        top_k=3,
        database=database
    )

    knowledge_base_info = ""
    if evaluation_knowledge:
        knowledge_base_info = "\n\n知识库中的评估标准参考：\n" + "\n".join([
            f"- {item['text']}" for item in evaluation_knowledge
        ])

    system_prompt = f"""你是一位专业的销售培训师，现在需要评估销售代表的话术。

【重要原则】
1. 你的评估必须基于知识库中的销售方法论和评估标准
2. 如果知识库中没有相关标准，基于行业最佳实践评估
3. 评估要客观、具体、有建设性
4. 不能编造不存在的评估标准

【对话上下文】
- 轮次：第{round_num}轮
- 场景：{scenario.get('name', '')}
- AI角色：{scenario.get('ai_role', '')}
- 销售代表说：{user_message}
- AI客户回应：{ai_response}

{knowledge_base_info}

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
        result = ai_client.chat_completion(
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.3,
            max_tokens=1000
        )

        if not result["success"]:
            logger.error(f"❌ AI评估失败: {result.get('error', 'Unknown error')}")
            return {
                "overall_score": 70,
                "dimension_scores": {},
                "feedback": "评估服务暂时不可用",
                "suggestions": []
            }

        result_text = result["content"]

        # 提取JSON（去掉可能的markdown代码块标记）
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        evaluation = json.loads(result_text)
        logger.info(f"✅ AI评估完成: 总分{evaluation.get('overall_score', 0)}")
        return evaluation

    except Exception as e:
        logger.error(f"❌ AI评估失败: {e}")
        return {
            "overall_score": 70,
            "dimension_scores": {},
            "feedback": "评估服务暂时不可用",
            "suggestions": []
        }

def call_ai_for_opening(
    scenario: dict,
    client_unit: str,
    product: str,
    scenario_type: str
) -> str:
    """
    调用AI生成开场白

    核心原则：
    1. 开场白必须符合场景特点
    2. 产品信息只能来自知识库
    3. 不能编造产品功能或价格
    """
    # 根据产品名称选择对应的数据库
    database = resolve_product_database(product)
    
    # 先检索相关的产品信息和场景话术
    product_knowledge = search_rag_knowledge(f"{product} 产品介绍", top_k=3, database=database)
    opening_knowledge = search_rag_knowledge(
        f"{scenario.get('name', '')} 开场话术 初次沟通",
        top_k=3,
        database=database
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

    system_prompt = f"""你现在完全沉浸在【{scenario['ai_role']}】这个角色中，作为{client_unit}的真实客户与销售代表进行初次沟通。

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
5. 可以加入一些自然的语气词或过渡语

【场景信息】
- 你所在单位：{client_unit}
- 你想了解的产品：{product}
- 沟通场景：{scenario_type}

{knowledge_context}

【开场白示例参考】
❌ 不要这样："你好，我想了解你们的商务视频彩铃产品，请介绍一下。"
✅ 应该这样：
   "你好，我是XX公司的采购经理，最近在考虑给公司做些彩铃方面的升级..."
   "你好，听说你们有视频彩铃这个产品，想具体了解一下..."

【现在开始】
请你作为{scenario['ai_role']}，用真实自然的语言说出开场白。
直接说出开场白，不要有任何解释或说明。"""

    try:
        result = ai_client.chat_completion(
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.8,
            max_tokens=300
        )

        if result["success"]:
            opening = result["content"]
            logger.info(f"✅ AI生成开场白: {opening[:50]}...")
            return opening
        else:
            logger.error(f"❌ 生成开场白失败: {result.get('error', 'Unknown error')}")
            return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"

    except Exception as e:
        logger.error(f"❌ 生成开场白失败: {e}")
        return f"你好，我是{client_unit}的{scenario['ai_role']}，听说你们有{product}产品？"

def call_ai_for_final_report(
    session_data: dict
) -> dict:
    """
    调用AI生成最终评估报告

    核心原则：
    1. 报告必须基于知识库中的销售培训标准
    2. 不能编造评估方法
    3. 所有建议必须来自知识库
    """
    if not ai_client:
        return _build_fallback_report(session_data)

    messages = session_data.get("messages", [])
    scenario = session_data.get("scenario", {})
    rounds = session_data.get("round", 0)

    # 根据产品名称选择对应的数据库（优先使用用户显式选择的）
    product = session_data.get("product", "")
    database = session_data.get("database") or resolve_product_database(product)

    # 检索销售培训标准和方法论
    training_standards = search_rag_knowledge(
        "销售培训标准 评估方法 销售方法论",
        top_k=5,
        database=database
    )

    knowledge_context = ""
    if training_standards:
        knowledge_context = "\n\n【知识库中的培训标准】\n" + "\n".join([
            f"- {item['text']}" for item in training_standards
        ])
    else:
        knowledge_context = "\n\n【注意】当前知识库中没有销售培训标准，请基于行业最佳实践评估。"

    # 构建对话摘要
    conversation_summary = ""
    for i, msg in enumerate(messages[-10:]):  # 最近10轮
        role = "客户" if msg.get("role") == "ai" else "销售代表"
        conversation_summary += f"\n{role}: {msg.get('content', '')}\n"

    system_prompt = f"""你是一位资深的销售培训专家，现在要对一场销售陪练对话进行总结评估。

【重要原则】
1. 评估标准必须来自知识库中的销售培训方法论
2. 不能编造不存在的评估方法
3. 所有建议必须基于知识库或行业最佳实践
4. 如果知识库中没有相关标准，明确说明

【对话信息】
- 场景：{scenario.get('name', '')}
- 轮次：{rounds}
- 客户单位：{session_data.get('client_unit', '')}
- 产品：{session_data.get('product', '')}

【对话摘要】
{conversation_summary}

{knowledge_context}

请以JSON格式返回评估报告：
{{
    "total_score": <总分0-100>,
    "rating_text": "<评级：优秀/良好/满意/待改进/较差>",
    "dimension_scores": {{
        "开场话术": {{"score": <分数>, "feedback": "<反馈>"}},
        "需求挖掘": {{"score": <分数>, "feedback": "<反馈>"}},
        "产品介绍": {{"score": <分数>, "feedback": "<反馈>"}},
        "异议处理": {{"score": <分数>, "feedback": "<反馈>"}},
        "促成技巧": {{"score": <分数>, "feedback": "<反馈>"}}
    }},
    "highlights": ["<亮点1>", "<亮点2>", "<亮点3>"],
    "improvements": ["<待改进1>", "<待改进2>", "<待改进3>"],
    "suggestions": ["<建议1>", "<建议2>", "<建议3>"],
    "detailed_analysis": {{
        "conversation_flow": "<对话流程分析>",
        "key_strengths": ["<优势1>", "<优势2>"],
        "focus_areas": ["<重点改进1>", "<重点改进2>"]
    }}
}}

只返回JSON，不要其他内容。"""

    try:
        result = ai_client.chat_completion(
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.3,
            max_tokens=2000
        )

        if not result["success"]:
            logger.error(f"❌ AI生成报告失败: {result.get('error', 'Unknown error')}")
            return _build_fallback_report(session_data)

        result_text = result["content"]

        # 提取JSON（支持多种格式：markdown代码块、纯JSON、JSON嵌在文本中）
        json_text = result_text.strip()

        # 1. 去掉markdown代码块
        if "```json" in json_text:
            json_text = json_text.split("```json")[1].split("```")[0].strip()
        elif "```" in json_text:
            json_text = json_text.split("```")[1].split("```")[0].strip()

        # 2. 如果不是以{开头，尝试找到第一个{和最后一个}
        if not json_text.startswith("{"):
            start = json_text.find("{")
            end = json_text.rfind("}")
            if start != -1 and end != -1:
                json_text = json_text[start:end+1]

        report = json.loads(json_text)

        # 确保必要字段存在
        if "total_score" not in report:
            report["total_score"] = _calc_avg_score(session_data)
        if "rating_text" not in report:
            report["rating_text"] = _score_to_rating(report["total_score"])
        for field in ["highlights", "improvements", "suggestions"]:
            if field not in report:
                report[field] = []

        logger.info(f"✅ AI生成报告: 总分{report.get('total_score', 0)}")
        return report

    except Exception as e:
        logger.error(f"❌ 生成报告失败: {e}")
        return _build_fallback_report(session_data)


def _calc_avg_score(session_data: dict) -> int:
    """从实时评估中计算平均分"""
    evaluations = session_data.get("evaluations", [])
    if evaluations:
        scores = [e.get("overall_score", 0) for e in evaluations if e.get("overall_score", 0) > 0]
        return round(sum(scores) / len(scores)) if scores else 70
    return 70


def _score_to_rating(score: int) -> str:
    """分数转评级文字"""
    if score >= 90:
        return "优秀"
    elif score >= 80:
        return "良好"
    elif score >= 70:
        return "满意"
    elif score >= 60:
        return "待改进"
    else:
        return "较差"


def _build_fallback_report(session_data: dict) -> dict:
    """基于实时评估数据构建兜底报告（AI不可用时使用）"""
    evaluations = session_data.get("evaluations", [])
    avg_score = _calc_avg_score(session_data)
    rounds = session_data.get("round", 0)

    # 从实时评估中提取建议
    all_suggestions = []
    for ev in evaluations:
        for s in ev.get("suggestions", []):
            if s and s not in all_suggestions:
                all_suggestions.append(s)

    highlights = []
    improvements = []
    if avg_score >= 80:
        highlights.append(f"共完成{rounds}轮对话，表现良好")
        if evaluations:
            highlights.append("对话过程中保持了较好的互动节奏")
    elif avg_score >= 60:
        highlights.append(f"共完成{rounds}轮对话")
        improvements.append("话术表达可以更加专业和自然")
        improvements.append("建议加强产品知识的掌握")
    else:
        improvements.append(f"共完成{rounds}轮对话，建议增加练习")
        improvements.append("话术流畅度有待提升")
        improvements.append("需要更多产品知识储备")

    return {
        "total_score": avg_score,
        "rating_text": _score_to_rating(avg_score),
        "dimension_scores": {},
        "highlights": highlights if highlights else [f"完成了{rounds}轮对话练习"],
        "improvements": improvements if improvements else ["继续保持练习"],
        "suggestions": all_suggestions[:5] if all_suggestions else ["建议多练习产品介绍和异议处理话术"],
        "detailed_analysis": {
            "conversation_flow": f"本次陪练共进行{rounds}轮对话。",
            "key_strengths": [],
            "focus_areas": ["产品知识", "话术表达"]
        }
    }

# ==================== API端点 ====================

@app.get("/")
async def root():
    """前端页面"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"error": "前端页面未找到"}

@app.get("/api/status")
async def api_status():
    """系统状态"""
    return {
        "status": "running",
        "message": "AI话术陪练系统正在运行",
        "ai_configured": ai_client is not None,
        "ai_provider": "MiniMax" if ai_client is not None else "未配置",
        "ai_model": config.MINIMAX_MODEL if ai_client is not None else None,
        "rag_service": config.RAG_SERVICE_URL,
        "principles": {
            "1": "所有对话必须由AI生成",
            "2": "所有知识必须来自RAG知识库",
            "3": "不允许编造产品信息"
        }
    }

@app.get("/scenarios")
async def get_scenarios():
    """获取所有场景"""
    return {
        "preset": scenarios,
        "custom_count": len([s for s in scenarios.values() if s.get("is_custom", False)])
    }

@app.post("/scenarios/create")
async def create_scenario(scenario: ScenarioCreate):
    """创建自定义场景"""
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
        "created_at": datetime.now().isoformat()
    }

    scenarios[scenario_id] = new_scenario

    # 保存到文件
    try:
        scenarios_file = Path(config.SCENARIOS_FILE)
        with open(scenarios_file, 'w', encoding='utf-8') as f:
            json.dump(scenarios, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存场景失败: {e}")

    return {
        "message": "场景创建成功",
        "scenario_id": scenario_id,
        "scenario": new_scenario
    }

@app.post("/session/start")
async def start_session(session_start: SessionStart):
    """开始陪练会话"""
    if not ai_client:
        raise HTTPException(
            status_code=500,
            detail="AI服务未配置，请在tutor_config.py中设置MINIMAX_API_KEY"
        )

    # 处理自定义场景
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
            "success_criteria": custom.success_criteria
        }
    else:
        if scenario_id not in scenarios:
            raise HTTPException(status_code=404, detail="场景不存在")
        scenario = scenarios[scenario_id]

    # 创建会话
    session_id = generate_session_id()

    session_data = {
        "session_id": session_id,
        "scenario": scenario,
        "client_unit": session_start.client_unit,
        "product": session_start.product,
        "scenario_type": session_start.scenario_type,
        "database": session_start.database,  # 用户显式选择的知识库
        "round": 0,
        "messages": [],
        "evaluations": [],
        "created_at": datetime.now().isoformat(),
        "status": "active"
    }

    # 生成场景提示（不是AI开场白，而是给用户的提示）
    scenario_hint = f"""你是{session_start.client_unit}的{scenario['ai_role']}。

【背景信息】
- 单位：{session_start.client_unit}
- 产品：{session_start.product}
- 场景：{session_start.scenario_type}
- 你的特点：{', '.join(scenario.get('customer_traits', []))}

现在请销售经理开始对话..."""

    # 不保存AI开场白，让用户先发言
    # session_data["messages"] 暂时为空

    # 保存会话
    sessions[session_id] = session_data
    save_session(session_id, session_data)

    return {
        "session_id": session_id,
        "scenario": scenario,
        "opening_message": scenario_hint,
        "user_should_start": True,  # 标记用户应该先开始
        "session_info": {
            "client_unit": session_start.client_unit,
            "product": session_start.product,
            "scenario_type": session_start.scenario_type
        }
    }

@app.post("/chat")
async def chat(chat_message: ChatMessage):
    """发送消息"""
    session_id = chat_message.session_id

    # 检查会话是否存在
    if session_id not in sessions:
        session_data = load_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        sessions[session_id] = session_data
    else:
        session_data = sessions[session_id]

    # 处理暂停获取反馈
    if chat_message.is_pause:
        if session_data["messages"]:
            last_user_msg = [m for m in session_data["messages"] if m["role"] == "user"][-1]
            last_ai_msg = [m for m in session_data["messages"] if m["role"] == "ai"][-1]
            
            # 根据产品名称选择对应的数据库（优先使用用户显式选择的）
            product = session_data.get("product", "")
            database = session_data.get("database") or resolve_product_database(product)

            # 使用AI评估
            evaluation = call_ai_for_evaluation(
                last_user_msg["content"],
                last_ai_msg["content"],
                session_data["round"],
                session_data["scenario"],
                "",
                database=database
            )

            return {
                "is_pause_response": True,
                "evaluation": evaluation,
                "ai_response": None
            }

    # 保存用户消息
    session_data["messages"].append({
        "role": "user",
        "content": chat_message.message,
        "timestamp": datetime.now().isoformat()
    })

    # 增加轮次
    session_data["round"] += 1

    # ========== 核心逻辑开始 ==========

    # 根据产品名称选择对应的数据库（优先使用用户显式选择的）
    product = session_data.get("product", "")
    database = session_data.get("database") or resolve_product_database(product)

    # 1. 从RAG知识库检索相关信息（这是最重要的！）
    # 检索产品信息、应对话术、成功案例等
    product_knowledge = search_rag_knowledge(
        f"{product} 产品介绍 功能 价格",
        top_k=3,
        database=database
    )
    sales_knowledge = search_rag_knowledge(
        f"{session_data['scenario'].get('name', '')} 应对话术 销售技巧",
        top_k=3,
        database=database
    )
    objection_knowledge = search_rag_knowledge(
        f"常见异议处理 价格异议 技术异议",
        top_k=2,
        database=database
    )

    # 2. 构建知识库上下文
    knowledge_context = "\n\n【重要：知识库信息（必须使用这些信息，不能编造）】\n"

    if product_knowledge:
        knowledge_context += "\n📦 产品信息（来自知识库）：\n"
        for item in product_knowledge:
            knowledge_context += f"- {item['text']}\n"
    else:
        knowledge_context += "\n⚠️  知识库中没有产品信息，请使用通用话术\n"

    if sales_knowledge:
        knowledge_context += "\n💬 应对话术（来自知识库）：\n"
        for item in sales_knowledge:
            knowledge_context += f"- {item['text']}\n"

    if objection_knowledge:
        knowledge_context += "\n⚡ 异议处理方法（来自知识库）：\n"
        for item in objection_knowledge:
            knowledge_context += f"- {item['text']}\n"

    logger.info(f"📚 知识库检索结果：产品{len(product_knowledge)}条，话术{len(sales_knowledge)}条，异议{len(objection_knowledge)}条")

    # 3. 构建对话历史
    conversation_history = []
    for msg in session_data["messages"][-5:]:
        role = "assistant" if msg["role"] == "ai" else "user"
        conversation_history.append({
            "role": role,
            "content": msg["content"]
        })

    # 4. 构建系统提示（严格限制只能使用知识库信息）
    scenario = session_data["scenario"]

    # 根据轮次决定提问策略
    round_num = session_data['round']

    # 提问策略模板（让AI自然地提问）
    question_templates = {
        1: [
            "我最近在了解{product}，想问一下...",
            "听说你们有{product}这个产品，能介绍一下吗？",
            "我们正在考虑{product}，想了解一下具体情况..."
        ],
        2: [
            "那具体来说，{product}的功能是怎样的？",
            "关于{product}，能不能详细说说它的特点？",
            "我想更深入了解{product}，能讲讲吗？"
        ],
        3: [
            "价格方面呢？{product}是怎么收费的？",
            "成本方面我们比较关心，{product}的价格大概是多少？",
            "预算方面我们需要考虑，{product}的费用情况如何？"
        ]
    }

    # 构建角色要求
    role_requirements = f"""
【角色深度要求】
你现在完全沉浸在【{scenario['ai_role']}】这个角色中：

1. 语言风格必须符合{scenario['ai_role']}的身份：
   - 使用符合该角色的专业术语和表达方式
   - 体现该角色的性格特点和沟通习惯
   - 保持角色的情绪状态和关注焦点

2. 行为特征必须展现{scenario['name']}的特点：
   - {chr(10).join([f'   - {t}' for t in scenario.get('customer_traits', ['关注需求'])])}

3. 沟通策略必须符合场景设计：
   - {chr(10).join([f'   - {s}' for s in scenario.get('ai_strategy', ['自然沟通'])])}

4. 自然提问要求（非常重要）：
   - 将知识库中的问题融入到真实对话中，不要像查资料一样直接问
   - 用客户的口吻和关注点来包装问题，体现真实需求
   - 问题之间要有逻辑关联，符合对话流程
   - 可以先表达感受、疑虑或需求，再自然引出问题
   - 避免连续生硬提问，要在对话中穿插反馈和思考
"""

    system_prompt = f"""你是一位专业的销售培训师，现在扮演【{scenario['ai_role']}】与销售代表进行真实的商务对话。

{role_requirements}

【🔴 核心原则（必须严格遵守）】
1. 你只能使用下面"知识库信息"中的内容来提及产品和功能
2. 绝对不能编造知识库中没有的产品功能、价格或特性
3. 如果知识库中没有相关信息，用客户的方式表达疑虑，如"这个我不太清楚""能详细说说吗"
4. 优先提出知识库中的问题，但要包装成真实的客户疑问

【对话场景】
- 客户单位：{session_data['client_unit']}
- 感兴趣的产品：{session_data['product']}
- 沟通场景：{session_data['scenario_type']}
- 对话轮次：第{round_num}轮

【知识库信息（你可以基于这些内容提出客户疑问）】
{knowledge_context}

【对话要求】
1. 第{round_num}轮对话，你应该{'深入提问' if round_num > 1 else '初步了解产品'}，符合当前对话阶段
2. 提问要自然，用客户的语言表达，不要像面试官或考官
3. 可以先表达："我们比较关注...""我想了解一下...""这方面能不能..."
4. 问题之间要有衔接，体现真实的思考过程
5. 适当穿插反馈："原来是这样""嗯，了解了""哦..."
6. 保持角色的情绪和态度，展现真实客户的状态

【示例对话风格】
❌ 不要这样："你们的产品的核心功能有哪些？请介绍一下具体特点。"
✅ 应该这样："我最近在看一些类似的产品，想了解一下你们这个主要解决什么问题？"

现在请作为{scenario['ai_role']}，用自然的客户语言回复销售代表。记住：你是真实的客户，不是机器人！"""

    # 5. 调用AI生成回复
    ai_response = call_ai_for_response(
        system_prompt,
        conversation_history,
        chat_message.message
    )

    # 6. 使用AI评估用户话术
    evaluation = call_ai_for_evaluation(
        chat_message.message,
        ai_response,
        session_data["round"],
        scenario,
        knowledge_context,
        database=database
    )

    # ========== 核心逻辑结束 ==========

    # 保存AI回复
    session_data["messages"].append({
        "role": "ai",
        "content": ai_response,
        "timestamp": datetime.now().isoformat()
    })

    session_data["evaluations"].append(evaluation)

    # 保存会话
    save_session(session_id, session_data)

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
            "objection_knowledge": len(objection_knowledge)
        }
    }

@app.post("/session/end")
async def end_session(session_end: SessionEnd):
    """结束会话并生成报告"""
    session_id = session_end.session_id

    # 加载会话
    if session_id in sessions:
        session_data = sessions[session_id]
    else:
        session_data = load_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")

    # 更新会话状态
    session_data["status"] = "completed"
    session_data["ended_at"] = datetime.now().isoformat()

    # 简版报告直接复用实时评估，避免结束会话时再次触发慢速 RAG + LLM 生成。
    if session_end.detail_level == "simple":
        report = _build_fallback_report(session_data)
    else:
        report = call_ai_for_final_report(session_data)

    # 添加基本信息
    report["session_id"] = session_id
    report["scenario"] = session_data["scenario"]["name"]
    report["rounds"] = session_data["round"]
    report["timestamp"] = datetime.now().isoformat()

    # 将报告保存到会话文件中，方便历史记录查看
    session_data["report"] = report
    save_session(session_id, session_data)

    # 从内存移除
    if session_id in sessions:
        del sessions[session_id]

    return report

@app.get("/history")
async def get_history():
    """获取历史会话列表"""
    try:
        sessions_dir = Path(config.SESSIONS_DIR)
        history = []

        for session_file in sessions_dir.glob("*.json"):
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # 提取报告中的评分信息（如果有）
            report = session_data.get("report", {})
            score = report.get("total_score", None)
            rating = report.get("rating_text", None)

            history.append({
                "session_id": session_data["session_id"],
                "scenario": session_data["scenario"]["name"],
                "rounds": session_data["round"],
                "status": session_data["status"],
                "created_at": session_data["created_at"],
                "client_unit": session_data.get("client_unit", ""),
                "product": session_data.get("product", ""),
                "score": score,
                "rating": rating
            })

        # 按时间倒序
        history.sort(key=lambda x: x["created_at"], reverse=True)

        return {"history": history}

    except Exception as e:
        logger.error(f"获取历史记录失败: {e}")
        return {"history": []}

@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    session_data = load_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")

    return session_data

# ==================== 启动信息 ====================

def check_port_available(port):
    """检查端口是否可用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except socket.error:
            return False

if __name__ == "__main__":
    import uvicorn
    import sys

    print("=" * 60)
    print("  AI话术陪练系统 - RAG增强版")
    print("=" * 60)
    print()

    # 检查端口是否被占用
    if not check_port_available(config.TUTOR_SERVICE_PORT):
        print(f"[ERROR] 端口 {config.TUTOR_SERVICE_PORT} 已被占用！")
        print("请先处理占用该端口的进程，然后再启动系统。")
        print(f"您可以使用以下命令查看占用端口的进程：")
        print(f"  netstat -ano | findstr :{config.TUTOR_SERVICE_PORT}")
        print(f"然后使用以下命令终止进程：")
        print(f"  taskkill /PID <进程ID> /F")
        print()
        print("程序将退出...")
        sys.exit(1)

    if ai_client:
        print("[OK] MiniMax AI已配置")
        print(f"[OK] 使用模型：{config.MINIMAX_MODEL}")
    else:
        print("[!] MiniMax AI未配置")
        print("[!] 请在tutor_config.py中设置MINIMAX_API_KEY")

    print(f"[OK] RAG服务：{config.RAG_SERVICE_URL}")
    print()
    print("【核心原则】")
    print("  1. [OK] 所有对话由AI生成")
    print("  2. [OK] 所有知识来自RAG知识库")
    print("  3. [OK] 不允许编造产品信息")
    print()
    print(f"API地址: http://{config.TUTOR_SERVICE_HOST}:{config.TUTOR_SERVICE_PORT}")
    print(f"API文档: http://{config.TUTOR_SERVICE_HOST}:{config.TUTOR_SERVICE_PORT}/docs")
    print()
    print("启动中...")

    uvicorn.run(
        app,
        host=config.TUTOR_SERVICE_HOST,
        port=config.TUTOR_SERVICE_PORT,
        log_level="info"
    )
