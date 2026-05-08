#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键执行 skill 规范化生成流程：
- 读取 skill_pipeline_config.json
- 调用 run_skill_compliance_suite.py
- 保存最近一次执行报告
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = Path(__file__).resolve().parent
    cfg_path = root / "skill_pipeline_config.json"
    report_path = root / "training_output" / "_skill_pipeline_last_report.json"
    runner = root / "run_skill_compliance_suite.py"

    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")
    if not runner.exists():
        raise FileNotFoundError(f"执行脚本不存在: {runner}")

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    args = [
        sys.executable,
        str(runner),
        "--rag-url",
        str(cfg.get("rag_url", "http://localhost:8003")),
        "--database",
        str(cfg.get("database", "商务彩铃")),
        "--client-unit",
        str(cfg.get("client_unit", "联调测试公司")),
        "--listener-role",
        str(cfg.get("listener_role", "市场总监")),
        "--relation",
        str(cfg.get("relation", "良好关系")),
        "--audience",
        str(cfg.get("audience", "政企客户")),
        "--training-duration",
        str(cfg.get("training_duration", "半天（3-4小时）")),
        "--question-count",
        str(int(cfg.get("question_count", 20))),
        "--timeout",
        str(int(cfg.get("timeout", 120))),
    ]

    max_attempts = int(cfg.get("max_attempts", 3))
    max_attempts = max(1, min(max_attempts, 5))
    payload: dict = {}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    for attempt in range(1, max_attempts + 1):
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            payload = {
                "ok": False,
                "error": "无法解析执行输出为 JSON",
                "raw_output": output,
                "return_code": result.returncode,
            }
        payload["attempt"] = attempt
        payload["max_attempts"] = max_attempts
        if payload.get("ok"):
            break

    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if bool(payload.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
