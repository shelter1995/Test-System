#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
功能链路自动烟测：
- 陪练系统
- 方案编制
- 测试题生成

全部通过 rag-anything-api(8003) 的新知识库入口验证检索可用性。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class Case:
    chain: str
    query: str


DEFAULT_CASES: list[Case] = [
    Case("陪练", "商务视频彩铃资费是多少"),
    Case("陪练", "商务视频彩铃适合哪些客户场景"),
    Case("方案编制", "商务视频彩铃核心卖点"),
    Case("方案编制", "商务视频彩铃行业应用场景"),
    Case("测试题", "商务视频彩铃产品介绍"),
    Case("测试题", "价格异议处理话术"),
]


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response type: {type(data)}")
    return data


def get_json(url: str, timeout: int) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected response type: {type(data)}")
    return data


def run(base_url: str, database: str, timeout: int, top_k: int) -> tuple[bool, dict[str, Any]]:
    report: dict[str, Any] = {
        "base_url": base_url,
        "database": database,
        "db_exists": False,
        "chains": {},
        "cases": [],
    }

    db_list = get_json(f"{base_url}/db/list", timeout=timeout)
    databases = db_list.get("databases", [])
    ids = {str(item.get("id", "")).strip() for item in databases if isinstance(item, dict)}
    report["db_exists"] = database in ids
    if not report["db_exists"]:
        report["error"] = f"database not found: {database}; current={sorted(x for x in ids if x)}"
        return False, report

    all_ok = True
    for case in DEFAULT_CASES:
        payload = {
            "query": case.query,
            "n_results": top_k,
            "database": database,
        }
        try:
            data = post_json(f"{base_url}/ai_enhanced_search", payload, timeout=timeout)
            results = data.get("results", []) or []
            ok = len(results) > 0
            text_head = ""
            if results and isinstance(results[0], dict):
                text_head = str(results[0].get("text", ""))[:120].replace("\n", " ")
            item = {
                "chain": case.chain,
                "query": case.query,
                "ok": ok,
                "result_count": len(results),
                "text_head": text_head,
            }
            report["cases"].append(item)
            if not ok:
                all_ok = False
            chain_acc = report["chains"].setdefault(case.chain, {"total": 0, "passed": 0})
            chain_acc["total"] += 1
            if ok:
                chain_acc["passed"] += 1
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            report["cases"].append(
                {
                    "chain": case.chain,
                    "query": case.query,
                    "ok": False,
                    "error": str(exc),
                }
            )

    for chain, info in report["chains"].items():
        info["ok"] = info["passed"] == info["total"]
        if not info["ok"]:
            all_ok = False

    report["ok"] = all_ok
    return all_ok, report


def main() -> int:
    parser = argparse.ArgumentParser(description="验证三条业务链路是否使用新知识库并可检索")
    parser.add_argument("--base-url", default="http://localhost:8003", help="RAG API 地址")
    parser.add_argument("--database", default="商务彩铃", help="知识库 ID")
    parser.add_argument("--timeout", type=int, default=90, help="请求超时（秒）")
    parser.add_argument("--top-k", type=int, default=5, help="每次检索条数")
    args = parser.parse_args()

    ok, report = run(
        base_url=str(args.base_url).rstrip("/"),
        database=args.database,
        timeout=args.timeout,
        top_k=max(1, args.top_k),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
