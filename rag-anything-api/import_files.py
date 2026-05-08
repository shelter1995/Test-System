"""
使用 RAG-Anything 官方流程导入文件到知识库
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import config
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".gif",
    ".webp",
}


def collect_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_FORMATS else []

    files = []
    if recursive:
        for root, _, names in os.walk(path):
            for name in names:
                child = Path(root) / name
                if child.suffix.lower() in SUPPORTED_FORMATS:
                    files.append(child)
    else:
        for child in path.iterdir():
            if child.is_file() and child.suffix.lower() in SUPPORTED_FORMATS:
                files.append(child)
    return files


async def import_files(path: str, database: str, recursive: bool = False) -> tuple[int, int]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(str(source))

    files = collect_files(source, recursive=recursive)
    if not files:
        logger.warning(f"未找到支持格式文件: {source}")
        logger.info(f"支持格式: {', '.join(sorted(SUPPORTED_FORMATS))}")
        return 0, 0

    registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
    service = RAGAnythingService(
        storage_root=config.RAGANYTHING_STORAGE_ROOT,
        output_root=config.RAGANYTHING_OUTPUT_ROOT,
        registry=registry,
    )

    logger.info(f"开始导入数据库: {database}")
    logger.info(f"文件总数: {len(files)}")

    success = 0
    fail = 0
    for idx, file_path in enumerate(files, 1):
        logger.info(f"[{idx}/{len(files)}] 处理: {file_path.name}")
        try:
            await service.ingest_file(database, file_path)
            success += 1
        except Exception as e:
            fail += 1
            logger.error(f"导入失败: {file_path} -> {e}")

    logger.info("=" * 60)
    logger.info(f"导入完成: 成功 {success}, 失败 {fail}")
    return success, fail


def main():
    import argparse

    parser = argparse.ArgumentParser(description="使用 RAG-Anything 导入文件到知识库")
    parser.add_argument("path", help="文件路径或目录路径")
    parser.add_argument("--database", "-d", default="default", help="数据库名称 (默认: default)")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归处理子目录")
    args = parser.parse_args()

    try:
        asyncio.run(import_files(args.path, args.database, args.recursive))
    except FileNotFoundError:
        logger.error(f"路径不存在: {args.path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"导入失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
