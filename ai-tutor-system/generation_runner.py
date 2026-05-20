"""
内容生成运行器 v4

两管线：
- solution:  RAG → SCQA+MECE 结构化方案（温度 0.4，固定章节模板）
- training:  RAG → 3 次独立 MiniMax 调用 → 讲义 + 测试题 + README
"""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
JOBS_DIR = ROOT / "ai-tutor-system" / "tutor_data" / "generation_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = ROOT / "generation_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ARTIFACT_DIRS = ["generation_output"]

MAX_RUNNING_JOBS = int(os.getenv("GENERATION_MAX_RUNNING_JOBS", "1"))

# Lock to protect the check-and-create sequence in create_job
_create_job_lock = threading.Lock()


class ContentValidationError(RuntimeError):
    """内容验证失败（如 Markdown 过短、缺少标题等），不可重试。"""
    pass


# ==================== 客户端 ====================

_ai_client = None
_rag_client = None


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
                model=getattr(config, "MINIMAX_MODEL", "MiniMax-M2.7"),
                timeout=300,
                max_retries=2,
            )
            logger.info("内容生成器：MiniMax AI 已初始化 (timeout=300s)")
    except Exception as e:
        logger.error(f"内容生成器：MiniMax 初始化失败: {e}")
    return _ai_client


def _get_rag_client():
    global _rag_client
    if _rag_client is not None:
        return _rag_client
    try:
        from rag_client import get_rag_client
        _rag_client = get_rag_client()
    except Exception as e:
        logger.error(f"内容生成器：RAG 客户端初始化失败: {e}")
    return _rag_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_job(job: dict) -> None:
    (JOBS_DIR / f"{job['job_id']}.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_job_stage(job_id: str, stage: str) -> None:
    job = get_job(job_id)
    if job:
        job["stage"] = stage
        _save_job(job)


def _update_job_warnings(job_id: str, warnings: list[str]) -> None:
    if not warnings:
        return
    job = get_job(job_id)
    if job:
        existing = job.get("warnings") if isinstance(job.get("warnings"), list) else []
        job["warnings"] = existing + [item for item in warnings if item not in existing]
        _save_job(job)


def _safe_filename(text: str) -> str:
    text = str(text or "").strip()
    safe = re.sub(r'[^\w一-鿿._\-]', '_', text)
    return safe[:60] or "untitled"


def _running_jobs_count() -> int:
    count = 0
    for path in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"跳过损坏的作业文件 {path.name}: {exc}")
            continue
        if job.get("status") == "running":
            count += 1
    return count


# ==================== RAG 检索 ====================

def _search_for_solution(database: str) -> dict:
    rag = _get_rag_client()
    if not rag:
        return {}
    queries = [
        f"{database} 产品介绍 核心功能 价值",
        f"{database} 应用场景 行业方案 案例",
        f"{database} 成功案例 客户反馈 效果数据",
        f"{database} 差异化优势 竞品对比",
        f"{database} 实施部署 服务流程",
    ]
    logger.info(f"RAG 检索（解决方案）：{len(queries)} 路 → {database}")
    return rag.multi_query_search(queries, database, n_results=5, use_enhanced=True)


def _search_for_training(database: str, customer_group: str = "") -> dict:
    rag = _get_rag_client()
    if not rag:
        return {}
    group = customer_group or "企业客户"
    queries = [
        f"{database} 产品功能 技术参数 操作流程",
        f"{group} {database} 客户痛点 行业需求",
        f"{database} 销售话术 异议处理 促成技巧",
        f"{database} 成功案例 实施效果",
        f"{database} 常见问题 注意事项",
    ]
    logger.info(f"RAG 检索（培训）：{len(queries)} 路 → {database}")
    return rag.multi_query_search(queries, database, n_results=5, use_enhanced=True)


def _validate_markdown_artifact(content: str, artifact_name: str) -> None:
    text = str(content or "").strip()
    if len(text) < 80:
        raise ContentValidationError(f"{artifact_name} 生成内容过短")
    if "#" not in text:
        raise ContentValidationError(f"{artifact_name} 缺少 Markdown 标题")


# ==================== RAG 格式化 ====================

def build_context_block(context_result: dict) -> str:
    """将 /context API 返回结果格式化为带来源标注的文本块。"""
    lines = []
    for index, item in enumerate(context_result.get("contexts") or [], start=1):
        metadata = item.get("metadata") or {}
        source = metadata.get("source", "unknown")
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(f"[资料 {index} | 来源: {source}]\n{text}")
    return "\n\n".join(lines)


def _format_rag_results(rag_results: dict) -> str:
    if not rag_results:
        return '（知识库暂无相关内容，请基于专业知识生成。）'
    blocks = []
    for query, results in rag_results.items():
        if str(query).startswith("_"):
            continue
        if not results:
            continue
        blocks.append(f"\n### {query}")
        for i, r in enumerate(results[:3], 1):
            content = str(r.get("text", r.get("content", "")))[:600]
            metadata = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
            db_name = metadata.get("database", "")
            source_list = metadata.get("sources", [])
            source_label = db_name or "知识库"
            if source_list:
                source_label += "（文件：" + "、".join(source_list[:5]) + "）"
            score = r.get("score", 0)
            blocks.append(f"\n片段{i} [来源：{source_label} 相关度:{score:.0%}]\n{content}\n")
    return "\n".join(blocks) if blocks else "（检索完成但无有效内容。）"


def _rag_warnings(rag_results: dict) -> list[str]:
    warnings = rag_results.get("_warnings") if isinstance(rag_results, dict) else []
    return warnings if isinstance(warnings, list) else []


# ==================== MiniMax 调用 ====================

def _call_minimax(prompt: str, max_tokens: int = 8000, timeout: int = None, temperature: float = 0.7) -> str:
    client = _get_ai_client()
    if not client:
        raise RuntimeError("AI 服务未配置")

    if timeout and timeout != client.timeout:
        import tutor_config as config
        from minimax_client import MiniMaxClient
        active = MiniMaxClient(
            api_key=config.MINIMAX_API_KEY,
            model=getattr(config, "MINIMAX_MODEL", "MiniMax-M2.7"),
            timeout=timeout, max_retries=2,
        )
    else:
        active = client

    result = active.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature, max_tokens=max_tokens,
    )
    if not result.get("success"):
        raise RuntimeError(f"AI 生成失败 [{result.get('error_type','?')}]: {result.get('error','')}")
    content = result.get("content", "").strip()
    if not content:
        raise RuntimeError("AI 返回空内容")
    return content


# ==================== 解决方案 Prompt ====================

def _build_solution_prompt(request: dict, rag_results: dict) -> str:
    db_name = request.get("database", "产品知识库")
    knowledge_text = _format_rag_results(rag_results)

    return f"""你是「{db_name}」领域的资深解决方案专家。

请严格按照以下章节模板，为指定客户撰写一份专业解决方案文档。

---

## 客户信息

- 客户单位：{request.get("client_unit") or "未指定"}
- 决策人职位：{request.get("decision_maker_role") or "未指定"}
- 客情关系：{request.get("relationship_level") or "未指定"}
- 决策关注点：{request.get("decision_focus") or "未指定"}
- 决策流程：{request.get("decision_process") or "未指定"}
- 决策时间：{request.get("decision_timeline") or "未指定"}

## 客户痛点

- 主要挑战：{request.get("pain_challenges") or "未提供"}
- 应用场景：{request.get("pain_scenarios") or "未提供"}
- 对现状不满：{request.get("pain_dissatisfaction") or "未提供"}

## 知识库内容

{knowledge_text}

---

## 必须严格遵循的章节模板

以下每一章、每一节都必须出现，标题不可增删改：

```
# [客户单位] {db_name}解决方案

## 一、SCQA 架构分析

### 1.1 S 情境
（行业现状与背景，2-3段）

### 1.2 C 冲突
（客户面临的具体痛点与挑战，结合客户提供的痛点信息）

### 1.3 Q 核心问题
（提炼核心问题，1-2句）

### 1.4 A 答案概述
（提出{db_name}作为答案的核心理由）

## 二、产品功能配置 (MECE)

### 2.1 基础功能模块
（逐项展开，每项3-5句）

### 2.2 增值功能模块
（逐项展开，每项3-5句）

## 三、应用场景方案 (MECE)

（按客户行业和业务场景细分，至少3个场景。每个含：场景描述 + 方案详述 + 预期效果）

## 四、实施计划 (MECE)

### 4.1 前期准备
（具体任务 + 时间安排）

### 4.2 部署实施
（具体任务 + 时间安排）

### 4.3 培训优化
（具体任务 + 时间安排）

## 五、营销话术

### 5.1 开场话术
### 5.2 产品介绍话术
### 5.3 价值阐述话术
### 5.4 异议处理话术（至少2个场景的完整对话）
### 5.5 促成话术
```

## 关键要求

1. 每条信息标注源文件：📄来源：`文件名`
2. 严禁编造功能/数据/日期/版本号/文档编号
3. 基于知识库内容，不虚构
4. 总字数 ≥ 2000 字
5. 使用 Markdown，直接输出文档，不要任何前言后语。"""


# ==================== 培训三阶段 Prompt ====================

def _build_manual_prompt(request: dict, rag_results: dict) -> str:
    db_name = request.get("database", "产品知识库")
    knowledge_text = _format_rag_results(rag_results)

    return f"""你是「{db_name}」领域的资深培训设计师，精通 Gagne 九段教学法和 Kolb 体验式学习。

请撰写一份完整的培训讲义。

---

## 培训配置

- 领域：{db_name}
- 主题：{request.get("training_theme") or "产品培训"}
- 目标客户群：{request.get("target_customer_group") or "企业客户"}
- 培训对象：{request.get("trainee_level") or "新入职人员"}（基础：{request.get("trainee_base") or "无经验"}）
- 时长：{request.get("duration") or "半天（3-4小时）"}
- 目标：{request.get("training_goals") or "能够介绍产品"}
- 重点：{request.get("focus_areas") or "产品知识"}

---

## 知识库内容

{knowledge_text}

---

## 结构要求（严格按此顺序）

```
# {db_name} 培训讲义

## 课程信息
（培训主题、时长、对象、目标）

## 学习目标（布鲁姆分类）
- [记忆] 能说出...
- [理解] 能解释...
- [应用] 能根据客户特点匹配方案...
- [分析] 能分析竞品差异...
- [创造] 能独立设计话术...

## 第一部分：课程导入（{request.get("duration", "3小时")}的10%时间）
### 1. 引起注意（痛点案例）
（完整案例：背景+问题+结果，≥200字）
### 2. 告知目标
### 3. 激活旧知

## 第二部分：产品知识（25%时间，MECE分类）
### 产品定位与核心价值
### 功能模块详解（每个3-5句展开）
### 产品优势对比
### 成功案例（≥2个，每个≥200字：背景+挑战+方案+效果+关键话术）

## 第三部分：客户痛点分析（行业矩阵）
### 按客户类型分类的痛点
### 痛点挖掘话术（完整对话示例）

## 第四部分：销售演练（35%时间，Kolb循环）
### 场景一演练（含角色设定+场景背景+流程+评分标准100分）
### 场景二演练（同上）
### Kolb循环：体验→反思→概念→实践

## 第五部分：异议处理话术库
（≥3种异议，每种含客户心理分析+应对策略+完整对话脚本）

## 第六部分：总结与行动清单
### 一页纸速查表
### 课后行动计划
```

## 要求
1. 禁止提纲式——所有内容必须完整展开
2. 每条信息标注源文件：📄来源：`文件名`
3. 话术是完整对话脚本，不是要点列表
4. 案例 ≥200字/个
5. 严厉禁止编造日期/版本号/文档编号
6. 总字数 ≥ 4000 字
7. Markdown 格式，直接输出文档。"""


def _build_exam_prompt(request: dict, rag_results: dict, manual_summary: str) -> str:
    db_name = request.get("database", "产品知识库")

    # 题型配置
    question_config = request.get("exam_question_config")
    if question_config and isinstance(question_config, list) and len(question_config) > 0:
        type_lines = []
        total = 0
        for item in question_config:
            t = item.get("type", "")
            c = item.get("count", 0)
            total += c
            type_lines.append(f"- {t}：{c} 题")
        exam_types_str = "\n".join(type_lines)
        exam_count = total
    else:
        exam_count = request.get("exam_question_count") or 20
        exam_types_str = "- 选择题：5 题\n- 填空题：3 题\n- 简答题：4 题\n- 案例分析题：3 题\n- 附加题：1 题"

    diff = request.get("exam_difficulty_distribution") or {"基础": 50, "进阶": 30, "挑战": 20}
    if isinstance(diff, dict):
        diff_str = f"基础 {diff.get('基础',50)}% / 进阶 {diff.get('进阶',30)}% / 挑战 {diff.get('挑战',20)}%"
    else:
        diff_str = str(diff)

    total_score = request.get("exam_total_score") or 100
    pass_score = request.get("exam_pass_score") or 80

    # 截取讲义前1500字作为上下文
    summary = (manual_summary or "")[:1500]

    return f"""你是「{db_name}」领域的培训考核专家，精通布鲁姆认知分类法。

请基于以下讲义摘要和知识库内容，设计一套培训测试题。

---

## 考试配置

总题量：{exam_count} 题
题型分布：
{exam_types_str}
难度分布：{diff_str}
总分：{total_score} 分 | 合格线：{pass_score} 分

---

## 讲义摘要（供出题参考）

{summary}

---

## 知识库内容

{_format_rag_results(rag_results)}

---

## 题目格式要求

必须包含以下题型板块，每题严格按此格式：

### 一、选择题（记忆层+理解层）
每题格式：
**题号. [考察层级] 题干**
A. ...  B. ...  C. ...  D. ...
> 答案：X
> 解析：...（说明为什么选这个）
> 分值：X 分

### 二、填空题（记忆层）
**题号. [记忆] 题干（含填空横线）**
> 答案：...
> 解析：...
> 分值：X 分

### 三、简答题（理解层+应用层）
**题号. [理解/应用] 题干**
> 参考答案要点：
> 1. ...
> 2. ...
> 评分标准：每个要点X分

### 四、案例分析题（分析层+创造层）
**题号. [分析/创造] 案例背景 + 问题**
> 参考答案：
> 评分标准：

### 五、实践/附加题（创造层）
**题号. [创造] 任务描述**
> 评分标准：

---

## 答案速查表

| 题号 | 答案 | 分值 |
|------|------|------|
| 一-1 | ... | ... |
| ... | ... | ... |

---

## 要求

1. 每题必须完整，不缺题干、不缺答案、不缺解析、不缺分值
2. 考题覆盖布鲁姆全部层级（记忆→理解→应用→分析→创造）
3. 严禁编造日期/版本号
4. Markdown 格式，直接输出。"""


def _build_readme_prompt(request: dict) -> str:
    db_name = request.get("database", "产品知识库")
    theme = request.get("training_theme") or "产品培训"
    duration = request.get("duration") or "半天（3-4小时）"
    customer_group = request.get("target_customer_group") or "企业客户"
    trainee_level = request.get("trainee_level") or "新入职人员"

    return f"""你是「{db_name}」领域的培训管理专家。

请为以下培训材料撰写一份使用说明（README）。

---

培训主题：{theme}
目标客户群：{customer_group}
培训对象：{trainee_level}
培训时长：{duration}

---

## README 结构

```
# 培训材料使用说明

## 1. 材料概览
本套培训材料包含三个文件：
- 培训讲义.md — 完整培训教材
- 测试题（含答案）.md — 考核试题及答案解析
- 使用说明.md — 本文件

## 2. 培训前准备
（设备、场地、材料打印、角色扮演道具等，列出清单）

## 3. 培训中执行建议
按 Gagne 九段逐段说明讲师操作要点

## 4. 培训后跟进计划
（考核安排、行动跟踪、回访计划）

## 5. 培训效果评估（柯氏四级）
- Level 1 反应层：课后满意度调查
- Level 2 学习层：测试成绩 ≥ 80 分合格
- Level 3 行为层：培训后 1 个月跟踪
- Level 4 结果层：培训前后 3 个月业务数据对比
```

## 要求

1. 内容完整可直接使用
2. 严禁编造日期/版本号/文档编号
3. Markdown 格式，直接输出。"""


# ==================== 生成函数 ====================

def _generate_solution(request: dict, job_id: str = None) -> dict:
    db_name = request.get("database", "default")
    client_unit = request.get("client_unit") or "客户"

    rag_results = _search_for_solution(db_name)
    if job_id:
        _update_job_warnings(job_id, _rag_warnings(rag_results))
    prompt = _build_solution_prompt(request, rag_results)

    if job_id:
        _update_job_stage(job_id, "generating")

    content = _call_minimax(prompt, max_tokens=8000, temperature=0.4)
    _validate_markdown_artifact(content, "解决方案")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{_safe_filename(db_name)}_{_safe_filename(client_unit)}_解决方案_{ts}.md"
    return {"content": content, "filename": filename}


def _generate_training(request: dict, job_id: str = None) -> dict:
    db_name = request.get("database", "default")
    customer_group = request.get("target_customer_group") or ""

    # RAG 检索（只需一次）
    rag_results = _search_for_training(db_name, customer_group)
    if job_id:
        _update_job_warnings(job_id, _rag_warnings(rag_results))

    # 第1次：生成讲义
    if job_id:
        _update_job_stage(job_id, "generating_manual")
    manual_prompt = _build_manual_prompt(request, rag_results)
    manual_content = _call_minimax(manual_prompt, max_tokens=8000, timeout=600, temperature=0.5)
    _validate_markdown_artifact(manual_content, "培训讲义")

    # 第2次：生成测试题（传入讲义摘要做上下文）
    if job_id:
        _update_job_stage(job_id, "generating_exam")
    exam_prompt = _build_exam_prompt(request, rag_results, manual_content)
    exam_content = _call_minimax(exam_prompt, max_tokens=6000, timeout=600, temperature=0.5)
    _validate_markdown_artifact(exam_content, "测试题")

    # 第3次：生成 README
    if job_id:
        _update_job_stage(job_id, "generating_readme")
    readme_prompt = _build_readme_prompt(request)
    readme_content = _call_minimax(readme_prompt, max_tokens=4000, timeout=300, temperature=0.5)
    _validate_markdown_artifact(readme_content, "使用说明")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_db = _safe_filename(db_name)

    return {"files": [
        {"content": manual_content, "filename": f"{safe_db}_培训讲义_{ts}.md"},
        {"content": exam_content, "filename": f"{safe_db}_测试题_{ts}.md"},
        {"content": readme_content, "filename": f"{safe_db}_使用说明_{ts}.md"},
    ]}


_GENERATORS = {"solution": _generate_solution, "training": _generate_training}
_TYPE_NAMES = {"solution": "解决方案", "training": "培训材料"}


# ==================== 公共接口 ====================

def _run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    request = job.get("request", {})
    gen_type = request.get("type", "solution")
    try:
        generator = _GENERATORS.get(gen_type)
        if not generator:
            raise ValueError(f"未知生成类型: {gen_type}")

        job["stage"] = "searching"
        _save_job(job)

        output = generator(request, job_id=job_id)

        saved_files = []
        if gen_type == "solution":
            fp = OUTPUT_DIR / output["filename"]
            fp.write_text(output["content"], encoding="utf-8")
            saved_files.append({"filename": output["filename"], "path": str(fp.relative_to(ROOT)), "size": fp.stat().st_size})
        elif gen_type == "training":
            for f in output.get("files", []):
                fp = OUTPUT_DIR / f["filename"]
                fp.write_text(f["content"], encoding="utf-8")
                saved_files.append({"filename": f["filename"], "path": str(fp.relative_to(ROOT)), "size": fp.stat().st_size})

        job["status"] = "completed"
        job["stage"] = "done"
        job["result"] = {"type": gen_type, "type_name": _TYPE_NAMES.get(gen_type, gen_type), "files": saved_files}
        job["finished_at"] = _now()
        _save_job(job)
        return None

    except Exception as e:
        logger.error(f"生成作业 {job_id} 失败: {e}")
        job["status"] = "failed"
        job["stage"] = "error"
        job["error"] = str(e)
        job["error_type"] = e.__class__.__name__
        # 只有超时和网络错误是可重试的；内容验证失败和一般 RuntimeError 不可重试
        job["retryable"] = isinstance(e, (TimeoutError, ConnectionError))
        job["finished_at"] = _now()
        _save_job(job)


def create_job(request: dict) -> str:
    with _create_job_lock:
        if _running_jobs_count() >= MAX_RUNNING_JOBS:
            raise RuntimeError(f"已有 {MAX_RUNNING_JOBS} 个生成作业正在运行，请稍后再试")

        job_id = uuid.uuid4().hex[:12]
        job = {"job_id": job_id, "status": "running", "stage": "init",
               "created_at": _now(), "request": request, "result": None, "error": None}
        _save_job(job)

    # 后台线程使用 daemon=True；进程退出时正在运行的作业会被强制中断
    worker = threading.Thread(
        target=_run_job,
        args=(job_id,),
        name=f"generation-job-{job_id}",
        daemon=True,
    )
    worker.start()
    return job_id


def get_job(job_id: str) -> dict | None:
    if not re.match(r'^[0-9a-f]{12}$', job_id):
        return None
    path = JOBS_DIR / f"{job_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_artifacts() -> list[dict]:
    artifacts = []
    for d in ARTIFACT_DIRS:
        dp = ROOT / d
        if dp.exists():
            for f in sorted(dp.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                artifacts.append({
                    "name": f.name, "path": str(f.relative_to(ROOT)),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                })
    return artifacts
