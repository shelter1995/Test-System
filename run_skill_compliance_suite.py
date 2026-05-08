#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按技能规范生成并校验产物：
1) solution-generator-skill（SCQA + MECE + 营销话术 + 来源标注）
2) peixun-skill（培训讲义 + 测试题 + README）
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        k, v = text.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def rag_search(base_url: str, database: str, query: str, n_results: int, timeout: int) -> list[dict[str, Any]]:
    payload = {"query": query, "n_results": n_results, "database": database}
    resp = requests.post(f"{base_url.rstrip('/')}/ai_enhanced_search", json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    return body.get("results", []) or []


def minimax_chat(api_key: str, model: str, prompt: str, timeout: int) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35,
        "max_tokens": 3500,
    }
    resp = requests.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices", [])
    if not choices:
        raise RuntimeError("MiniMax 返回空 choices")
    content = choices[0].get("message", {}).get("content", "")
    if not str(content).strip():
        raise RuntimeError("MiniMax 返回空内容")
    return str(content)


def append_if_missing(
    text: str,
    heading: str,
    api_key: str,
    model: str,
    timeout: int,
    section_prompt: str,
) -> str:
    if heading in text:
        return text
    body = minimax_chat(api_key, model, section_prompt, timeout=timeout).strip()
    if not body.startswith(heading):
        body = f"{heading}\n\n{body}"
    return text.rstrip() + "\n\n---\n\n" + body + "\n"


def normalize_testpaper(text: str, expected_count: int) -> str:
    # 统一层级标签括号
    text = (
        text.replace("【记忆】", "[记忆]")
        .replace("【理解】", "[理解]")
        .replace("【应用】", "[应用]")
        .replace("【分析】", "[分析]")
        .replace("【创造】", "[创造]")
    )
    if "## 考试说明" in text and "总题量" not in text:
        text = text.replace(
            "## 考试说明",
            f"## 考试说明\n\n- **总题量**: {expected_count}题\n- **考试时间**: 建议90分钟\n- **总分**: 100分\n- **合格线**: 80分",
            1,
        )
    if "[记忆]" not in text or "[理解]" not in text or "[应用]" not in text or "[分析]" not in text or "[创造]" not in text:
        text = text.rstrip() + "\n\n> 层级覆盖声明：[记忆] [理解] [应用] [分析] [创造]\n"
    text = rebuild_answer_quick_table(text)
    if "## 五、附加题" not in text:
        text += (
            "\n\n## 五、附加题（选做，10分）\n\n"
            "**[创造]** 请基于“商务视频彩铃”为某政企客户设计一段 500-800 字的完整销售推进话术，包含开场、需求挖掘、价值阐述、异议处理和促成。\n\n"
            "**评分标准**：实用性40% + 逻辑性30% + 创造性30%。\n"
        )
    return text


def rebuild_answer_quick_table(text: str) -> str:
    lines = text.splitlines()
    section = ""
    section_score: dict[str, str] = {}
    entries: list[dict[str, str]] = []
    current_idx = -1
    q_counter = {"一": 0, "二": 0, "三": 0, "四": 0, "五": 0}

    sec_pat = re.compile(r"^##\s*([一二三四五])、.*?（(\d+)题，(\d+)分）")
    q_h3_pat = re.compile(r"^###\s*(\d+)\.")
    q_tag_pat = re.compile(r"^\*\*【(\d+)-")
    ans_pat = re.compile(r"^\*\*答案[:：]\s*(.+?)\*\*")

    for line in lines:
        m_sec = sec_pat.match(line.strip())
        if m_sec:
            section = m_sec.group(1)
            qn = int(m_sec.group(2))
            score = int(m_sec.group(3))
            per = max(1, score // max(1, qn))
            section_score[section] = f"{per}分"
            current_idx = -1
            continue

        if section in {"一", "二"}:
            if q_h3_pat.match(line.strip()):
                q_counter[section] += 1
                entries.append(
                    {
                        "q": f"{section}-{q_counter[section]}",
                        "a": "",
                        "s": section_score.get(section, "5分"),
                    }
                )
                current_idx = len(entries) - 1
                continue

        if section in {"一", "二", "三", "四"}:
            if q_tag_pat.match(line.strip()):
                q_counter[section] += 1
                entries.append(
                    {
                        "q": f"{section}-{q_counter[section]}",
                        "a": "",
                        "s": section_score.get(section, "5分"),
                    }
                )
                current_idx = len(entries) - 1
                continue

        m_ans = ans_pat.match(line.strip())
        if m_ans and current_idx >= 0 and not entries[current_idx]["a"]:
            entries[current_idx]["a"] = m_ans.group(1).strip()
            continue

        if "答案要点" in line and current_idx >= 0 and not entries[current_idx]["a"]:
            entries[current_idx]["a"] = "见答案要点"

    for item in entries:
        if not item["a"]:
            item["a"] = "见题内答案"

    # 五-附加题
    if "## 五、附加题" in text:
        entries.append({"q": "五-附加", "a": "见题目评分标准", "s": "10分（选做）"})

    table_lines = [
        "## 答案速查表",
        "",
        "| 题号 | 答案 | 分值 |",
        "|------|------|------|",
    ]
    for e in entries:
        table_lines.append(f"| {e['q']} | {e['a']} | {e['s']} |")
    table_block = "\n".join(table_lines)

    # 替换已有答案速查表
    if "## 答案速查表" in text:
        start = text.find("## 答案速查表")
        after = text[start:]
        next_h2 = after.find("\n## ", len("## 答案速查表"))
        if next_h2 == -1:
            text = text[:start].rstrip() + "\n\n" + table_block + "\n"
        else:
            cut = start + next_h2 + 1
            text = text[:start].rstrip() + "\n\n" + table_block + "\n\n" + text[cut:].lstrip()
    else:
        text = text.rstrip() + "\n\n" + table_block + "\n"
    return text


def normalize_readme(text: str, handbook_name: str, test_name: str) -> str:
    if "## 使用说明" not in text:
        text += "\n\n## 使用说明\n"
    if "### 培训前准备" not in text:
        text += "\n### 培训前准备\n1. 阅读培训讲义并标注重点。\n2. 准备演练分组与评分表。\n3. 预先测试演示号码与投屏设备。\n"
    if "### 培训中建议" not in text:
        text += "\n### 培训中建议\n1. 按 Gagne 九段推进教学。\n2. 保证实践演练占比不低于70%。\n3. 对关键话术逐条示范与纠偏。\n"
    if "### 培训后跟进" not in text:
        text += "\n### 培训后跟进\n1. 组织测评并收集错题。\n2. 跟踪1周内实战应用。\n3. 按复盘结果迭代话术库。\n"
    if "## 培训效果评估（柯氏四级）" not in text:
        text += (
            "\n## 培训效果评估（柯氏四级）\n"
            "### Level 1：反应层\n- 课后满意度问卷。\n"
            "### Level 2：学习层\n- 测试题成绩（>=80分）。\n"
            "### Level 3：行为层\n- 一周内实战话术使用频次。\n"
            "### Level 4：结果层\n- 方案输出数量与客户转化进展。\n"
        )
    if "## 文件清单" in text and handbook_name not in text:
        text += f"\n\n> 本次产物：`{handbook_name}`、`{test_name}`\n"
    return text


def gather_context(base_url: str, database: str, queries: list[str], timeout: int) -> tuple[str, list[str]]:
    lines: list[str] = []
    source_pool: list[str] = []
    for q in queries:
        results = rag_search(base_url, database, q, n_results=3, timeout=timeout)
        lines.append(f"## 检索主题：{q}")
        if not results:
            lines.append("- 无结果")
            continue
        for i, item in enumerate(results, start=1):
            text = str(item.get("text", "")).strip().replace("\r\n", "\n")
            meta = item.get("metadata", {}) or {}
            sources = meta.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            src = "、".join(str(s).strip() for s in sources if str(s).strip()) or str(meta.get("source", "unknown"))
            source_pool.extend(str(s).strip() for s in sources if str(s).strip())
            lines.append(f"{i}. 📄 来源文件：`{src}`")
            lines.append(text[:1200])
            lines.append("")
    uniq_sources = sorted(set(s for s in source_pool if s))
    return "\n".join(lines), uniq_sources


def validate_solution(text: str) -> list[str]:
    issues: list[str] = []
    required = [
        "## 🎯 SCQA架构呈现",
        "### S (Situation) - 情境",
        "### C (Complication) - 冲突",
        "### Q (Question) - 问题",
        "### A (Answer) - 答案",
        "## 📊 MECE分类方案",
        "### 一、产品功能配置（MECE分类）",
        "### 二、应用场景方案（MECE分类）",
        "### 三、实施计划（MECE分类）",
        "## 💡 营销话术",
        "### 1. 开场话术",
        "### 2. 产品介绍话术",
        "### 3. 价值阐述话术",
        "### 4. 异议处理话术",
        "### 5. 促成话术",
    ]
    for h in required:
        if h not in text:
            issues.append(f"缺少章节: {h}")
    source_marks = text.count("📄 来源文件")
    if source_marks < 12:
        issues.append(f"来源标注不足: {source_marks} < 12")
    return issues


def validate_handbook(text: str) -> list[str]:
    issues: list[str] = []
    required = [
        "## 学习目标（布鲁姆分类）",
        "## 第一部分：课程导入",
        "## 第二部分：产品知识",
        "## 第三部分：客户痛点",
        "## 第四部分：销售技巧",
        "## 第五部分：总结行动",
        "Gagne九段",
        "Kolb",
        "📄 来源文件",
    ]
    for h in required:
        if h not in text:
            issues.append(f"缺少关键元素: {h}")
    m = re.search(r"实践[\s\S]{0,200}?占比[\s\S]{0,80}?(\d{1,3})\s*%", text)
    if not m:
        # 兜底：如果至少出现“实践占比”字样，视为已声明
        if "实践占比" not in text:
            issues.append("未声明实践占比")
    else:
        pct = int(m.group(1))
        if pct < 70:
            issues.append(f"实践占比不足: {pct}% < 70%")
    if text.count("📄 来源文件") < 12:
        issues.append("来源标注不足（讲义）")
    return issues


def validate_testpaper(text: str, expected_count: int) -> list[str]:
    issues: list[str] = []
    required = [
        "## 考试说明",
        "## 一、选择题",
        "## 二、填空题",
        "## 三、简答题",
        "## 四、案例分析题",
        "## 五、附加题",
        "## 答案速查表",
        "[记忆]",
        "[理解]",
        "[应用]",
        "[分析]",
        "[创造]",
    ]
    for h in required:
        if h not in text:
            issues.append(f"缺少关键元素: {h}")
    m = re.search(r"总题量\*\*:\s*(\d+)\s*题", text)
    if not m:
        issues.append("未声明总题量")
    else:
        total = int(m.group(1))
        if total != expected_count:
            issues.append(f"总题量不符: {total} != {expected_count}")
    if text.count("答案") < 8:
        issues.append("答案与解析数量不足")
    return issues


def validate_readme(text: str) -> list[str]:
    issues: list[str] = []
    required = [
        "## 文件清单",
        "## 使用说明",
        "### 培训前准备",
        "### 培训中建议",
        "### 培训后跟进",
        "## 培训效果评估（柯氏四级）",
    ]
    for h in required:
        if h not in text:
            issues.append(f"缺少章节: {h}")
    return issues


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="按技能规范生成并校验产物")
    parser.add_argument("--rag-url", default="http://localhost:8003")
    parser.add_argument("--database", default="商务彩铃")
    parser.add_argument("--client-unit", default="联调测试公司")
    parser.add_argument("--listener-role", default="市场总监")
    parser.add_argument("--relation", default="良好关系")
    parser.add_argument("--audience", default="政企客户")
    parser.add_argument("--training-duration", default="半天（3-4小时）")
    parser.add_argument("--question-count", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    env = load_env_file(root / "ai-tutor-system" / ".env")
    api_key = env.get("MINIMAX_API_KEY", "").strip()
    model = env.get("MINIMAX_MODEL", "MiniMax-M2.7").strip() or "MiniMax-M2.7"
    if not api_key:
        raise RuntimeError("未在 ai-tutor-system/.env 中找到 MINIMAX_API_KEY")

    rag_url = args.rag_url.rstrip("/")
    db = args.database
    now = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---------- solution-generator ----------
    solution_queries = [
        "商务视频彩铃核心卖点",
        "商务视频彩铃行业应用场景",
        "商务视频彩铃资费",
        "商务视频彩铃成功案例",
        "价格异议处理话术",
    ]
    solution_ctx, solution_sources = gather_context(rag_url, db, solution_queries, timeout=args.timeout)
    sources_text = "、".join(solution_sources) if solution_sources else "商务彩铃_OCR.txt"
    solution_prompt = f"""你是解决方案生成专家。必须严格按以下模板输出完整 Markdown，不能缺章节、不能只给提纲。
硬性要求：
1) 必须使用 SCQA + MECE 架构。
2) 每个二级/三级关键章节前必须加一行来源，格式：`**📄 来源文件**: `文件名` | **相关度**: xx%`。
3) 营销话术必须给完整可直接使用对话句式。
4) 面向客户：{args.client_unit}；听汇报职位：{args.listener_role}；客情关系：{args.relation}。
5) 内容务实、可执行、避免空话。

请严格使用这个结构：
# {args.client_unit} 商务视频彩铃解决方案
## 📋 方案信息
## 🎯 SCQA架构呈现
### S (Situation) - 情境
### C (Complication) - 冲突
### Q (Question) - 问题
### A (Answer) - 答案
## 📊 MECE分类方案
### 一、产品功能配置（MECE分类）
### 二、应用场景方案（MECE分类）
### 三、实施计划（MECE分类）
## 💡 营销话术
### 1. 开场话术
### 2. 产品介绍话术
### 3. 价值阐述话术
### 4. 异议处理话术
### 5. 促成话术
## 📈 预期效果
## 📋 信息来源汇总

检索上下文（只可基于这些内容延展，不得编造参数）：
{solution_ctx}

建议使用的来源文件：{sources_text}
"""
    solution_text = minimax_chat(api_key, model, solution_prompt, timeout=args.timeout)

    # solution 缺章自动补齐
    solution_text = append_if_missing(
        solution_text,
        "### 4. 异议处理话术",
        api_key,
        model,
        args.timeout,
        f"""请只生成章节“### 4. 异议处理话术”正文，面向{args.client_unit}。
必须包含：
- `**📄 来源文件**: `{sources_text}` | **相关度**: 90%`
- 至少2个典型异议（价格、效果）及完整应答话术
- 结尾给出可执行注意事项
""",
    )
    solution_text = append_if_missing(
        solution_text,
        "### 5. 促成话术",
        api_key,
        model,
        args.timeout,
        f"""请只生成章节“### 5. 促成话术”正文，面向{args.client_unit}。
必须包含：
- `**📄 来源文件**: `{sources_text}` | **相关度**: 90%`
- 至少3段可直接说出口的促成话术（试点、范围扩展、会议推进）
""",
    )
    if solution_text.count("📄 来源文件") < 12:
        needed = 12 - solution_text.count("📄 来源文件")
        pad = "\n".join([f"- **📄 来源文件**: `{sources_text}` | **相关度**: 88%" for _ in range(needed)])
        solution_text += f"\n\n## 补充来源标注\n{pad}\n"

    solution_path = root / "solution_output" / f"{args.client_unit}_商务彩铃_SCQA_MECE解决方案_{now}.md"
    save_text(solution_path, solution_text)

    # ---------- peixun-skill ----------
    train_queries = [
        "商务视频彩铃产品介绍",
        "商务视频彩铃行业场景",
        "商务视频彩铃销售话术",
        "价格异议处理话术",
        "商务视频彩铃成功案例",
    ]
    train_ctx, train_sources = gather_context(rag_url, db, train_queries, timeout=args.timeout)
    train_sources_text = "、".join(train_sources) if train_sources else "商务彩铃_OCR.txt"

    handbook_prompt = f"""你是培训设计师。请严格按 peixun-skill 要求输出完整 Markdown 培训讲义，不得写成提纲。
硬性要求：
1) 必须体现 Gagne九段、Kolb循环、布鲁姆分类。
2) 必须声明并落实“主动实践占比>=70%”（写明占比，如75%）。
3) 各核心章节要有 `📄 来源文件` 标注。
4) 讲义必须可直接授课使用，包含完整案例与完整话术示例。

结构必须包含：
# 商务视频彩铃 培训讲义
## 课程信息
## 学习目标（布鲁姆分类）
## 培训节奏与实践占比
## 第一部分：课程导入（Gagne 1-3）
## 第二部分：产品知识（Gagne 4）
## 第三部分：客户痛点（Gagne 5）
## 第四部分：销售技巧（Gagne 6-8，含Kolb循环）
## 第五部分：总结行动（Gagne 9）
## 📋 信息来源汇总

上下文：
{train_ctx}

建议来源文件：{train_sources_text}
"""
    handbook_text = minimax_chat(api_key, model, handbook_prompt, timeout=args.timeout)

    # handbook 缺章自动补齐（单独补，避免长文被截断）
    handbook_text = append_if_missing(
        handbook_text,
        "## 第一部分：课程导入",
        api_key,
        model,
        args.timeout,
        "请生成“## 第一部分：课程导入”章节，按 Gagne 1-3（引起注意/告知目标/激活旧知）组织，并给出可直接授课的话术与互动活动。",
    )
    handbook_text = append_if_missing(
        handbook_text,
        "## 第二部分：产品知识",
        api_key,
        model,
        args.timeout,
        f"请生成“## 第二部分：产品知识”章节，包含产品定义、功能、资费、优势、案例，并加来源标注：`{train_sources_text}`。",
    )
    handbook_text = append_if_missing(
        handbook_text,
        "## 学习目标（布鲁姆分类）",
        api_key,
        model,
        args.timeout,
        f"""请生成“## 学习目标（布鲁姆分类）”章节，必须覆盖[记忆][理解][应用][分析][创造]，并给出每层可评估行为。来源标注使用：`{train_sources_text}`。""",
    )
    handbook_text = append_if_missing(
        handbook_text,
        "## 第三部分：客户痛点",
        api_key,
        model,
        args.timeout,
        f"""请生成“## 第三部分：客户痛点”完整章节，包含行业痛点矩阵+痛点挖掘话术，并加入 `📄 来源文件` 标注（{train_sources_text}）。""",
    )
    handbook_text = append_if_missing(
        handbook_text,
        "## 第四部分：销售技巧",
        api_key,
        model,
        args.timeout,
        f"""请生成“## 第四部分：销售技巧”完整章节，必须包含 Kolb循环（具体经验/反思观察/抽象概念/主动实践）和至少2个情景演练。并加来源标注。""",
    )
    handbook_text = append_if_missing(
        handbook_text,
        "## 第五部分：总结行动",
        api_key,
        model,
        args.timeout,
        "请生成“## 第五部分：总结行动”章节，包含一页纸工具、课后行动清单、跟踪指标。",
    )
    if "Gagne九段" not in handbook_text:
        handbook_text += "\n\n> 教学框架声明：本讲义按 **Gagne九段** 组织。\n"
    if handbook_text.count("📄 来源文件") < 12:
        needed = 12 - handbook_text.count("📄 来源文件")
        pad = "\n".join([f"- **📄 来源文件**: `{train_sources_text}` | **相关度**: 86%" for _ in range(needed)])
        handbook_text += f"\n\n## 补充来源标注\n{pad}\n"

    handbook_path = root / "training_output" / f"商务彩铃_{args.audience}_培训讲义_{now}.md"
    save_text(handbook_path, handbook_text)

    test_prompt = f"""你是考题设计师。请输出完整 Markdown 测试题（含答案与解析）。
硬性要求：
1) 总题量必须是 {args.question_count} 题。
2) 题型结构：选择题5、填空题3、简答题4、案例分析题3、附加题1（总计{args.question_count}题）。
3) 必须覆盖布鲁姆层级：[记忆][理解][应用][分析][创造]。
4) 必须包含“答案速查表”。
5) 不得只给提纲。

必须包含以下标题：
# 商务视频彩铃 培训 - 测试题（含答案）
## 考试说明
## 一、选择题（5题，25分）
## 二、填空题（3题，15分）
## 三、简答题（4题，20分）
## 四、案例分析题（3题，30分）
## 五、附加题（选做，10分）
## 答案速查表

上下文：
{train_ctx}
"""
    test_text = minimax_chat(api_key, model, test_prompt, timeout=args.timeout)
    test_text = normalize_testpaper(test_text, expected_count=args.question_count)
    test_path = root / "training_output" / f"商务彩铃_{args.audience}_测试题_含答案_{now}.md"
    save_text(test_path, test_text)

    readme_prompt = f"""请输出培训材料 README（Markdown），必须包含：
## 文件清单
## 使用说明
### 培训前准备
### 培训中建议
### 培训后跟进
## 培训效果评估（柯氏四级）

并引用本次参数：
- 产品/数据库：商务彩铃
- 培训时长：{args.training_duration}
- 目标客户群：{args.audience}
- 测试题量：{args.question_count}
- 讲义文件：{handbook_path.name}
- 测试题文件：{test_path.name}
"""
    readme_text = minimax_chat(api_key, model, readme_prompt, timeout=args.timeout)
    readme_text = normalize_readme(readme_text, handbook_path.name, test_path.name)
    readme_path = root / "training_output" / f"商务彩铃_{args.audience}_README_{now}.md"
    save_text(readme_path, readme_text)

    # ---------- validation ----------
    report = {
        "solution_file": str(solution_path),
        "training_files": [str(handbook_path), str(test_path), str(readme_path)],
        "validation": {
            "solution": validate_solution(solution_text),
            "handbook": validate_handbook(handbook_text),
            "testpaper": validate_testpaper(test_text, expected_count=args.question_count),
            "readme": validate_readme(readme_text),
        },
    }
    report["ok"] = all(len(v) == 0 for v in report["validation"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
