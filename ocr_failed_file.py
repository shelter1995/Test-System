#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
兼容入口：将文件重新导入 RAG-Anything 知识库。

RAG-Anything 迁移后，不再使用旧图片处理器和旧向量库。需要 OCR 的复杂文档
请先转换为可提取文本的 PDF/DOCX/TXT/PPTX，再使用本脚本导入。
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


def import_file(file_path: str, database: str = "商务彩铃"):
    project_root = Path(__file__).resolve().parent
    importer = project_root / "rag-anything-api" / "import_files.py"
    command = [
        resolve_rag_python(),
        str(importer),
        file_path,
        "--database",
        database,
    ]
    return subprocess.run(command, check=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入文件到 RAG-Anything 知识库")
    parser.add_argument("file_path", help="要导入的文件路径")
    parser.add_argument("--database", "-d", default="商务彩铃", help="数据库标识")
    args = parser.parse_args()

    result = import_file(args.file_path, args.database)
    sys.exit(result.returncode)
