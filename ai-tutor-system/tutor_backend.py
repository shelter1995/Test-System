"""
AI话术陪练系统 - 后端服务（精简版）
路由层 — 业务逻辑已迁移至 tutor_services.py 和 tutor_streaming.py
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse
from pathlib import Path
from datetime import datetime
from io import BytesIO
from html import escape
from urllib.parse import quote
import json
import asyncio
import logging
import re

import tutor_config as config
from tutor_models import ScenarioCreate, SessionStart, ChatMessage, SessionEnd
from tutor_services import (
    AIService,
    SessionManager,
    ReportGenerator,
    build_rag_context_prompt,
    get_rag_service,
    get_ai_service,
)
from tutor_streaming import StreamingPipeline

# 配置日志
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="AI话术陪练系统",
    description="基于统一 LLM 和 RAG 知识库的智能角色扮演训练系统",
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

# ==================== 场景持久化 ====================


def _load_scenarios(path: Path | str | None = None) -> dict:
    """加载场景：默认场景 + 持久化的自定义场景。"""
    merged = {key: dict(value) for key, value in config.DEFAULT_SCENARIOS.items()}
    scenarios_path = Path(path or config.SCENARIOS_FILE)
    if not scenarios_path.exists():
        return merged
    try:
        saved = json.loads(scenarios_path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            raise ValueError("场景文件根节点必须是对象")
        for scenario_id, item in saved.items():
            if not isinstance(item, dict) or not item.get("is_custom"):
                continue
            value = dict(item)
            value["id"] = str(value.get("id") or scenario_id)
            merged[str(scenario_id)] = value
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.error("读取自定义场景失败: %s", exc)
    return merged


def _save_custom_scenarios(values: dict, path: Path | str | None = None) -> None:
    """原子保存自定义场景到 JSON 文件。"""
    scenarios_path = Path(path or config.SCENARIOS_FILE)
    scenarios_path.parent.mkdir(parents=True, exist_ok=True)
    custom = {
        key: value
        for key, value in values.items()
        if isinstance(value, dict) and value.get("is_custom")
    }
    temp_path = scenarios_path.with_name(f"{scenarios_path.name}.tmp")
    temp_path.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(scenarios_path)


# ==================== 全局状态 ====================

sessions = {}  # 内存活跃会话缓存
scenarios = _load_scenarios()

# 服务实例
ai_service = get_ai_service()
rag_service = get_rag_service()
report_gen = ReportGenerator(ai_service)
streaming_pipeline = StreamingPipeline(rag_service, ai_service)

# 日志 AI 状态。8002 不在启动时判定 LLM 可用性，避免与 8003 启动顺序产生误报。
logger.info("统一 LLM 由 8003 模型设置提供: %s", config.RAG_SERVICE_URL)


def _find_existing_evaluation(session_data: dict):
    """查找当前轮次是否已有评分（幂等性检查）。"""
    return next(
        (
            item for item in session_data.get("evaluations", [])
            if int(item.get("round", session_data["round"])) == int(session_data["round"])
        ),
        None,
    )


def _build_session_pdf(session_data: dict) -> bytes:
    """Render a training session report as a PDF file."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise HTTPException(status_code=500, detail="PDF export dependency missing: reportlab") from exc

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="陪练记录报告",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ChineseTitle",
            parent=base["Title"],
            fontName="STSong-Light",
            fontSize=18,
            leading=24,
            spaceAfter=8,
            textColor=colors.HexColor("#2c3e50"),
            wordWrap="CJK",
        ),
        "heading": ParagraphStyle(
            "ChineseHeading",
            parent=base["Heading2"],
            fontName="STSong-Light",
            fontSize=13,
            leading=18,
            spaceBefore=12,
            spaceAfter=8,
            textColor=colors.HexColor("#2c3e50"),
            borderPadding=(0, 0, 4, 0),
            borderColor=colors.HexColor("#3498db"),
            borderWidth=0,
            borderBottomWidth=1,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "ChineseBody",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#2c3e50"),
            wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "ChineseTableHeader",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#2c3e50"),
            wordWrap="CJK",
        ),
        "table_label": ParagraphStyle(
            "ChineseTableLabel",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#607d8b"),
            wordWrap="CJK",
        ),
        "table_cell": ParagraphStyle(
            "ChineseTableCell",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#2c3e50"),
            wordWrap="CJK",
        ),
    }

    def text(value) -> str:
        return escape(str(value or "")).replace("\n", "<br/>")

    def para(value, style_name: str = "body"):
        return Paragraph(text(value), styles[style_name])

    def bullet_list(items):
        return [Paragraph("• " + text(item), styles["body"]) for item in (items or [])]

    scenario = session_data.get("scenario") if isinstance(session_data.get("scenario"), dict) else {}
    report = session_data.get("report") if isinstance(session_data.get("report"), dict) else {}
    story = [
        Paragraph("AI 话术陪练记录报告", styles["title"]),
        Paragraph("会话摘要", styles["heading"]),
        Table(
            [
                [para("客户单位", "table_label"), para(session_data.get("client_unit"), "table_cell"), para("产品", "table_label"), para(session_data.get("product"), "table_cell")],
                [para("场景", "table_label"), para(scenario.get("name"), "table_cell"), para("轮次", "table_label"), para(session_data.get("round", 0), "table_cell")],
                [para("状态", "table_label"), para(session_data.get("status"), "table_cell"), para("总分", "table_label"), para(report.get("total_score", "暂无"), "table_cell")],
                [para("评级", "table_label"), para(report.get("rating_text", "暂无"), "table_cell"), para("会话ID", "table_label"), para(session_data.get("session_id"), "table_cell")],
            ],
            colWidths=[24 * mm, 58 * mm, 20 * mm, 58 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf4fa")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#edf4fa")),
                    ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#fbfdff")),
                    ("BACKGROUND", (3, 0), (3, -1), colors.HexColor("#fbfdff")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dcdcdc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        ),
    ]

    dims = report.get("dimension_scores") if isinstance(report.get("dimension_scores"), dict) else {}
    if dims:
        story.append(Paragraph("五维评分", styles["heading"]))
        rows = [[para("维度", "table_header"), para("分数", "table_header"), para("反馈", "table_header")]]
        for name, value in dims.items():
            value = value if isinstance(value, dict) else {}
            rows.append([
                para(name, "table_cell"),
                para(value.get("score", 0), "table_cell"),
                Paragraph(text(value.get("feedback", "")), styles["table_cell"]),
            ])
        story.append(
            Table(
                rows,
                colWidths=[28 * mm, 16 * mm, 116 * mm],
                style=TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf3fb")),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#ffffff")),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dcdcdc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                ),
                repeatRows=1,
            )
        )

    for title, key in [("亮点", "highlights"), ("改进点", "improvements"), ("建议", "suggestions")]:
        if report.get(key):
            story.append(Paragraph(title, styles["heading"]))
            story.extend(bullet_list(report.get(key)))

    messages = session_data.get("messages") if isinstance(session_data.get("messages"), list) else []
    if messages:
        story.append(Paragraph("对话记录", styles["heading"]))
        for item in messages:
            role = "销售代表" if item.get("role") == "user" else "AI客户"
            story.append(Paragraph(f"<b>{role}：</b>{text(item.get('content'))}", styles["body"]))
            story.append(Spacer(1, 5))

    doc.build(story)
    return buffer.getvalue()


def _safe_pdf_filename(session_data: dict) -> str:
    """Create a readable PDF filename from session context."""
    scenario = session_data.get("scenario") if isinstance(session_data.get("scenario"), dict) else {}
    parts = [
        "陪练记录",
        session_data.get("client_unit"),
        session_data.get("product"),
        scenario.get("name"),
    ]
    raw = "_".join(str(part).strip() for part in parts if str(part or "").strip())
    safe = re.sub(r'[\\/:*?"<>|\r\n]+', "_", raw).strip(" ._")
    if not safe:
        safe = str(session_data.get("session_id") or "陪练记录")
    if len(safe) > 120:
        safe = safe[:120].rstrip(" ._")
    return f"{safe}.pdf"


# ==================== API 端点 ====================

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
    runtime = ai_service.runtime_status(refresh=True)
    return {
        "status": "running",
        "message": "AI话术陪练系统正在运行",
        "ai_configured": runtime["available"],
        "ai_provider": runtime["provider"] if runtime["available"] else "未配置",
        "ai_model": runtime["model"] if runtime["available"] else None,
        "rag_service": config.RAG_SERVICE_URL,
    }


@app.get("/scenarios")
async def get_scenarios():
    """获取所有场景"""
    return {
        "preset": scenarios,
        "custom_count": len([s for s in scenarios.values() if s.get("is_custom")]),
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
        "created_at": datetime.now().isoformat(),
    }

    scenarios[scenario_id] = new_scenario
    try:
        _save_custom_scenarios(scenarios)
    except OSError as exc:
        scenarios.pop(scenario_id, None)
        logger.error("保存场景失败: %s", exc)
        raise HTTPException(status_code=500, detail="自定义场景保存失败") from exc

    return {
        "message": "场景创建成功",
        "scenario_id": scenario_id,
        "scenario": new_scenario,
    }


@app.post("/session/start")
async def start_session(session_start: SessionStart):
    """开始陪练会话"""
    if not ai_service.available:
        raise HTTPException(status_code=500, detail="AI服务未配置")

    # 处理场景
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

    if session_id not in sessions:
        session_data = SessionManager.load(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="会话不存在")
        sessions[session_id] = session_data
    else:
        session_data = sessions[session_id]

    # 处理暂停（评估请求）— 流式返回
    if chat_message.is_pause:
        if session_data["messages"]:
            last_user = [m for m in session_data["messages"] if m["role"] == "user"][-1]
            last_ai = [m for m in session_data["messages"] if m["role"] == "ai"][-1]
            product = session_data.get("product", "")
            database = session_data.get("database") or rag_service.resolve_database(product)

            existing = _find_existing_evaluation(session_data)

            async def pause_eval_stream():
                from tutor_models import SSEEvent
                if existing:
                    evaluation = existing
                else:
                    evaluation = await asyncio.to_thread(
                        ai_service.evaluate,
                        last_user["content"],
                        last_ai["content"],
                        session_data["round"],
                        session_data["scenario"],
                        "",
                        database=database,
                    )
                    evaluation["round"] = session_data["round"]
                    session_data.setdefault("evaluations", []).append(evaluation)
                    SessionManager.save(session_id, session_data)
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

            existing = _find_existing_evaluation(session_data)
            if existing:
                return {
                    "is_pause_response": True,
                    "evaluation": existing,
                    "ai_response": None,
                }

            evaluation = await asyncio.to_thread(
                ai_service.evaluate,
                last_user["content"],
                last_ai["content"],
                session_data["round"],
                session_data["scenario"],
                "",
                database=database,
            )
            evaluation["round"] = session_data["round"]
            session_data.setdefault("evaluations", []).append(evaluation)
            SessionManager.save(session_id, session_data)
            return {
                "is_pause_response": True,
                "evaluation": evaluation,
                "ai_response": None,
            }

    # 保存用户消息
    session_data["messages"].append({
        "role": "user",
        "content": chat_message.message,
        "timestamp": datetime.now().isoformat(),
    })
    session_data["round"] += 1

    product = session_data.get("product", "")
    database = session_data.get("database") or rag_service.resolve_database(product)

    # RAG 统一上下文检索
    context_query = f"{product} {session_data['scenario'].get('name', '')} 产品介绍 应对话术 常见异议处理"
    context_result = await asyncio.to_thread(
        rag_service.client.context,
        context_query,
        database,
        5,
    )
    knowledge_context = build_rag_context_prompt(context_result)

    from tutor_streaming import _build_system_prompt

    conversation_history = []
    for msg in session_data["messages"][-5:]:
        role = "assistant" if msg["role"] == "ai" else "user"
        conversation_history.append({"role": role, "content": msg["content"]})

    system_prompt = _build_system_prompt(
        scenario=session_data["scenario"],
        client_unit=session_data.get("client_unit", ""),
        product=product,
        scenario_type=session_data.get("scenario_type", ""),
        round_num=session_data["round"],
        knowledge_context=knowledge_context,
    )

    ai_response = await asyncio.to_thread(
        ai_service.generate_response,
        system_prompt,
        conversation_history,
        chat_message.message,
    )

    evaluation = await asyncio.to_thread(
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
            "knowledge_found": len(context_result.get("contexts") or []),
        },
    }


@app.post("/session/end")
async def end_session(session_end: SessionEnd):
    """结束会话并生成报告"""
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
        report = await asyncio.to_thread(report_gen.generate, session_data)

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
    """获取历史会话列表"""
    return {"history": SessionManager.list_all()}


@app.get("/session/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    session_data = SessionManager.load(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_data


@app.get("/session/{session_id}/export.pdf")
async def export_session_pdf(session_id: str):
    """导出陪练记录 PDF。"""
    session_data = SessionManager.load(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="会话不存在")

    pdf = _build_session_pdf(session_data)
    filename = _safe_pdf_filename(session_data)
    encoded = quote(filename)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="training-session.pdf"; filename*=UTF-8\'\'{encoded}'
            )
        },
    )


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除陪练历史记录。"""
    existed = SessionManager.delete(session_id)
    if not existed:
        raise HTTPException(status_code=404, detail="会话不存在")
    sessions.pop(session_id, None)
    return {"status": "success", "message": "Session deleted", "session_id": session_id}


# ==================== 启动 ====================

def check_port_available(port):
    """检查端口是否可用"""
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

    print("[OK] 统一 LLM：由 8003 模型设置提供")
    print("[OK] SSE 流式输出已启用")

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
