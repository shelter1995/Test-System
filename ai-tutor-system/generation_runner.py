"""
内容生成运行器 v2

支持4种独立内容类型：
- solution:  解决方案
- training:  培训教案
- exam:      考试题目
- readme:    使用说明

每种类型有独立的参数表单和生成逻辑，调用 MiniMax API 直接生成 Markdown。
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目根目录
ROOT = Path(__file__).parent.parent
JOBS_DIR = ROOT / "ai-tutor-system" / "tutor_data" / "generation_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = ROOT / "generation_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 产物搜索目录
ARTIFACT_DIRS = ["generation_output", "training_output", "solution_output"]

# ==================== MiniMax 客户端初始化 ====================

_ai_client = None


def _get_ai_client():
    global _ai_client
    if _ai_client is not None:
        return _ai_client

    try:
        import tutor_config as config
        from minimax_client import MiniMaxClient

        if config.MINIMAX_API_KEY and config.MINIMAX_API_KEY != "your_minimax_api_key_here":
            _ai_client = MiniMaxClient(
                api_key=config.MINIMAX_API_KEY,
                model=getattr(config, "MINIMAX_MODEL", "MiniMax-M2.7")
            )
            logger.info("内容生成器：MiniMax AI 已初始化")
        else:
            logger.warning("内容生成器：MiniMax API Key 未配置")
    except Exception as e:
        logger.error(f"内容生成器：初始化失败: {e}")

    return _ai_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_job(job: dict) -> None:
    path = JOBS_DIR / f"{job['job_id']}.json"
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_filename(text: str) -> str:
    """将文本转换为安全的文件名（不含非法字符）。"""
    text = str(text or "").strip()
    safe = re.sub(r'[^\w一-鿿._-]', '_', text)
    return safe[:60] or "untitled"


def _call_minimax(prompt: str, max_tokens: int = 4000) -> str:
    """调用 MiniMax API 生成内容，返回 Markdown 文本。"""
    client = _get_ai_client()
    if not client:
        raise RuntimeError("AI 服务未配置，请在 tutor_config.py 中设置 MINIMAX_API_KEY")

    messages = [{"role": "user", "content": prompt}]
    result = client.chat_completion(messages=messages, temperature=0.7, max_tokens=max_tokens)

    if not result.get("success"):
        raise RuntimeError(f"AI 生成失败: {result.get('error', '未知错误')}")

    content = result.get("content", "").strip()
    if not content:
        raise RuntimeError("AI 返回空内容")

    return content


# ==================== 各类型 Prompt 模板 ====================

_SOLUTION_PROMPT = """你是一位资深的企业解决方案顾问。请根据以下信息，撰写一份专业的产品解决方案文档。

【产品信息来源】
请基于知识库中的产品信息来撰写，确保信息准确，不编造未提及的功能或价格。

【客户背景】
- 客户单位：{client_unit}
- 产品：{product}
- 汇报对象/目标受众：{target_audience}

【文档要求】
1. 使用 Markdown 格式
2. 结构清晰，包含：项目背景、需求分析、解决方案、实施计划、预期效果
3. 语言专业、数据驱动
4. 突出产品价值，不夸大功能
5. 总字数不少于 1500 字

请直接输出完整的 Markdown 文档内容。"""

_TRAINING_PROMPT = """你是一位资深的企业培训师。请根据以下信息，撰写一份专业的培训教案。

【产品信息来源】
请基于知识库中的产品信息来撰写，确保信息准确。

【培训背景】
- 产品：{product}
- 目标受众：{target_audience}
- 培训时长：{duration}

【文档要求】
1. 使用 Markdown 格式
2. 结构包含：培训目标、课程大纲、详细内容（按时间分配）、互动环节、考核方式
3. 内容要有实操性，包含话术示例和案例
4. 总字数不少于 2000 字

请直接输出完整的 Markdown 培训教案。"""

_EXAM_PROMPT = """你是一位资深的培训考核专家。请根据以下信息，设计一套产品知识考试题目。

【产品信息来源】
请基于知识库中的产品信息来出题，确保题目有准确答案。

【考试背景】
- 产品：{product}
- 题量：{question_count} 道题
- 题目类型：{question_types}

【文档要求】
1. 使用 Markdown 格式
2. 每道题都要有标准答案和解析
3. 题目难度分布合理（基础:进阶:挑战 = 5:3:2）
4. 包含：单选题、多选题、判断题、简答题（根据类型要求调整）
5. 总字数不少于 1500 字

请直接输出完整的 Markdown 考试题目文档。"""

_README_PROMPT = """你是一位技术文档工程师。请根据以下信息，撰写一份专业的产品使用说明文档。

【产品信息来源】
请基于知识库中的产品信息来撰写，确保功能描述准确。

【产品背景】
- 产品：{product}
- 适用场景：{use_cases}

【文档要求】
1. 使用 Markdown 格式
2. 结构包含：产品简介、功能说明、使用步骤、注意事项、常见问题
3. 语言简洁明了，适合非技术人员阅读
4. 包含具体的操作步骤和截图占位符
5. 总字数不少于 1200 字

请直接输出完整的 Markdown 使用说明文档。"""


# ==================== 生成函数 ====================

def _generate_solution(request: dict) -> str:
    prompt = _SOLUTION_PROMPT.format(
        client_unit=request.get("client_unit") or "客户单位",
        product=request.get("product") or "产品",
        target_audience=request.get("target_audience") or "决策层",
    )
    return _call_minimax(prompt, max_tokens=4000)


def _generate_training(request: dict) -> str:
    prompt = _TRAINING_PROMPT.format(
        product=request.get("product") or "产品",
        target_audience=request.get("target_audience") or "销售团队",
        duration=request.get("duration") or "1小时",
    )
    return _call_minimax(prompt, max_tokens=4000)


def _generate_exam(request: dict) -> str:
    prompt = _EXAM_PROMPT.format(
        product=request.get("product") or "产品",
        question_count=request.get("question_count") or 20,
        question_types=request.get("question_types") or "单选、多选、简答",
    )
    return _call_minimax(prompt, max_tokens=4000)


def _generate_readme(request: dict) -> str:
    prompt = _README_PROMPT.format(
        product=request.get("product") or "产品",
        use_cases=request.get("use_cases") or "企业日常使用",
    )
    return _call_minimax(prompt, max_tokens=4000)


_GENERATORS = {
    "solution": _generate_solution,
    "training": _generate_training,
    "exam": _generate_exam,
    "readme": _generate_readme,
}

_TYPE_NAMES = {
    "solution": "解决方案",
    "training": "培训教案",
    "exam": "考试题目",
    "readme": "使用说明",
}


# ==================== 公共接口 ====================

def create_job(request: dict) -> str:
    """创建生成作业并在当前线程中同步执行（由 asyncio.to_thread 调用）。"""
    gen_type = request.get("type", "solution")
    job_id = uuid.uuid4().hex[:12]

    job = {
        "job_id": job_id,
        "status": "running",
        "created_at": _now(),
        "request": request,
        "result": None,
        "error": None,
    }
    _save_job(job)

    try:
        generator = _GENERATORS.get(gen_type)
        if not generator:
            raise ValueError(f"未知生成类型: {gen_type}")

        content = generator(request)

        # 保存产物
        product = _safe_filename(request.get("product") or "product")
        type_name = _TYPE_NAMES.get(gen_type, gen_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{product}_{type_name}_{timestamp}.md"
        file_path = OUTPUT_DIR / filename
        file_path.write_text(content, encoding="utf-8")

        job["status"] = "completed"
        job["result"] = {
            "filename": filename,
            "path": str(file_path.relative_to(ROOT)),
            "type": gen_type,
            "type_name": type_name,
            "size": file_path.stat().st_size,
        }
        job["finished_at"] = _now()
        _save_job(job)
        return job_id

    except Exception as e:
        logger.error(f"生成作业 {job_id} 失败: {e}")
        job["status"] = "failed"
        job["error"] = str(e)
        job["finished_at"] = _now()
        _save_job(job)
        return job_id


def get_job(job_id: str) -> dict | None:
    if not re.match(r'^[0-9a-f]{12}$', job_id):
        return None
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_artifacts() -> list[dict]:
    artifacts = []
    for output_dir_name in ARTIFACT_DIRS:
        dir_path = ROOT / output_dir_name
        if dir_path.exists():
            for f in sorted(dir_path.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                artifacts.append(
                    {
                        "name": f.name,
                        "path": str(f.relative_to(ROOT)),
                        "size": f.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
    return artifacts
