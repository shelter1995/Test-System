#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入文件夹到 RAG-Anything 知识库。
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


def ingest_folder(folder_path: str, database: str = "商务彩铃", recursive: bool = True):
    project_root = Path(__file__).resolve().parent
    importer = project_root / "rag-anything-api" / "import_files.py"
    command = [
        resolve_rag_python(),
        str(importer),
        folder_path,
        "--database",
        database,
    ]
    if recursive:
        command.append("--recursive")
    return subprocess.run(command, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入文件夹到 RAG-Anything 知识库")
    parser.add_argument("folder_path", help="要导入的文件夹路径")
    parser.add_argument("--database", "-d", default="商务彩铃", help="数据库标识")
    parser.add_argument("--no-recursive", action="store_true", help="不递归处理子目录")
    args = parser.parse_args()

    result = ingest_folder(args.folder_path, args.database, not args.no_recursive)
    sys.exit(result.returncode)
