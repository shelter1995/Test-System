#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入文件或目录到 RAG-Anything 知识库。
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


def import_path(path: str, database: str = "商务彩铃", recursive: bool = True):
    project_root = Path(__file__).resolve().parent
    importer = project_root / "rag-anything-api" / "import_files.py"
    command = [
        resolve_rag_python(),
        str(importer),
        path,
        "--database",
        database,
    ]
    if Path(path).is_dir() and recursive:
        command.append("--recursive")
    return subprocess.run(command, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入文件或目录到 RAG-Anything 知识库")
    parser.add_argument("path", help="文件或目录路径")
    parser.add_argument("--database", "-d", default="商务彩铃", help="数据库标识")
    parser.add_argument("--no-recursive", action="store_true", help="目录导入时不递归")
    args = parser.parse_args()

    result = import_path(args.path, args.database, not args.no_recursive)
    sys.exit(result.returncode)
