#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试单个文件导入 RAG-Anything。
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def resolve_rag_python() -> str:
    env_python = os.getenv("RAGANYTHING_PYTHON", "").strip()
    configured = Path(env_python) if env_python else None
    if configured and configured.exists():
        return str(configured)
    candidate = Path(r"D:\GitHub_WorkSpace\RAG-Anything\.venv\Scripts\python.exe")
    if candidate.exists():
        return str(candidate)
    return sys.executable


def test_single_file(file_path: str, database: str = "商务彩铃"):
    project_root = Path(__file__).resolve().parent
    importer = project_root / "rag-anything-api" / "import_files.py"
    command = [resolve_rag_python(), str(importer), file_path, "--database", database]
    return subprocess.run(command, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="测试单个文件导入 RAG-Anything")
    parser.add_argument("file_path", help="测试文件路径")
    parser.add_argument("--database", "-d", default="商务彩铃", help="数据库标识")
    args = parser.parse_args()

    result = test_single_file(args.file_path, args.database)
    sys.exit(result.returncode)
