#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端生成链路烟测：
1) 从 RAG-Anything 新知识库检索上下文
2) 调用 MiniMax 生成
3) 输出方案草案 + 测试题草案
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


def load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def rag_search(base_url: str, database: str, query: str, top_k: int, timeout: int) -> list[dict[str, Any]]:
    payload = {"query": query, "n_results": top_k, "database": database}
    resp = requests.post(f"{base_url}/ai_enhanced_search", json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    return body.get("results", []) or []


def minimax_chat(api_key: str, model: str, prompt: str, timeout: int) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 1800,
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
        raise RuntimeError("MiniMax empty choices")
    content = choices[0].get("message", {}).get("content", "")
    if not str(content).strip():
        raise RuntimeError("MiniMax empty content")
    return str(content)


def format_context(title: str, entries: list[dict[str, Any]]) -> str:
    lines = [f"## {title}"]
    for i, item in enumerate(entries, start=1):
        text = str(item.get("text", "")).strip()
        meta = item.get("metadata", {}) or {}
        source = meta.get("source", "unknown")
        lines.append(f"{i}. 来源: {source}")
        lines.append(text[:800])
    return "\n".join(lines)


def save_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="端到端生成链路烟测")
    parser.add_argument("--rag-url", default="http://localhost:8003")
    parser.add_argument("--database", default="商务彩铃")
    parser.add_argument("--client-unit", default="联调测试公司")
    parser.add_argument("--listener-role", default="市场总监")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    tutor_env = root / "ai-tutor-system" / ".env"
    env = load_env_file(tutor_env)
    api_key = env.get("MINIMAX_API_KEY", "").strip()
    model = env.get("MINIMAX_MODEL", "MiniMax-M2.7").strip() or "MiniMax-M2.7"
    if not api_key:
        raise RuntimeError(f"MINIMAX_API_KEY not found: {tutor_env}")

    rag_url = str(args.rag_url).rstrip("/")
    database = args.database

    # 方案编制链路上下文
    solution_queries = [
        "商务视频彩铃核心卖点",
        "商务视频彩铃行业应用场景",
        "商务视频彩铃成功案例",
        "商务视频彩铃资费",
    ]
    solution_context_parts = []
    for q in solution_queries:
        results = rag_search(rag_url, database, q, top_k=3, timeout=args.timeout)
        solution_context_parts.append(format_context(q, results))

    # 测试题链路上下文
    test_queries = [
        "商务视频彩铃产品介绍",
        "价格异议处理话术",
        "客户画像与场景匹配",
    ]
    test_context_parts = []
    for q in test_queries:
        results = rag_search(rag_url, database, q, top_k=3, timeout=args.timeout)
        test_context_parts.append(format_context(q, results))

    solution_prompt = f"""你是售前方案专家。基于以下知识库检索结果，输出一份完整 Markdown 方案草案。
要求：
1. 必须使用给定上下文，不要编造产品参数。
2. 结构：客户背景、痛点、方案设计、实施计划、价值收益、风险与应对、行动建议。
3. 内容面向 {args.client_unit} 的 {args.listener_role}，语言务实可执行。
4. 在末尾列出“引用来源（按检索主题）”。

{chr(10).join(solution_context_parts)}
"""

    test_prompt = f"""你是培训考题设计专家。基于以下知识库检索结果，输出一份完整 Markdown 测试题草案。
要求：
1. 题量 12 题：选择题 6、判断题 2、简答题 2、案例题 2。
2. 每题给出答案与简短解析。
3. 题目覆盖：产品能力、资费、应用场景、异议处理。
4. 在文末列出“引用来源（按检索主题）”。

{chr(10).join(test_context_parts)}
"""

    solution_md = minimax_chat(api_key, model, solution_prompt, timeout=args.timeout)
    test_md = minimax_chat(api_key, model, test_prompt, timeout=args.timeout)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    solution_path = root / "solution_output" / f"商务彩铃_方案草案_{now}.md"
    test_path = root / "training_output" / f"商务彩铃_测试题草案_{now}.md"
    save_markdown(solution_path, solution_md)
    save_markdown(test_path, test_md)

    print(
        json.dumps(
            {
                "status": "ok",
                "database": database,
                "solution_file": str(solution_path),
                "test_file": str(test_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
