"""
将导出的迁移数据导入到 RAG-Anything 知识库。
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import config
from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATION_DIR = os.path.join(os.path.dirname(__file__), "migration_data")
PRIORITY_ORDER = [
    "商务彩铃",
    "business_video_ringtone",
    "ccs_gyl",
    "keyexams",
]


def _document_source(db_id: str, index: int, doc: dict) -> str:
    metadata = doc.get("metadata") if isinstance(doc, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    source = str(metadata.get("source") or doc.get("source") or f"{db_id}.json").strip()
    if metadata.get("chunk") is not None:
        return f"{source}#chunk-{metadata.get('chunk')}"
    return f"{source}#doc-{index}"


async def import_database(service: RAGAnythingService, db_id: str, documents: list):
    """将一个数据库的迁移文本通过 RAG-Anything 服务层导入。"""
    logger.info(f"\n导入数据库: {db_id} ({len(documents)} 条)")

    success_count = 0
    fail_count = 0

    for i, doc in enumerate(documents, 1):
        text = doc.get("text", "")
        if not text or len(text.strip()) < 10:
            continue

        try:
            await service.ingest_text(db_id, text.strip(), source=_document_source(db_id, i, doc))
            success_count += 1
            if i % 10 == 0:
                logger.info(f"  进度: {i}/{len(documents)} (成功: {success_count})")
        except Exception as e:
            fail_count += 1
            if fail_count <= 5:
                logger.warning(f"  第 {i} 条导入失败: {str(e)[:100]}")

    logger.info(f"  完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count, fail_count


def _migration_database_ids(migration_dir: str) -> list[str]:
    root = Path(migration_dir)
    existing = {path.stem for path in root.glob("*.json")}
    ordered = [db_id for db_id in PRIORITY_ORDER if db_id in existing]
    ordered.extend(sorted(existing - set(ordered)))
    return ordered


async def main():
    """导入所有数据"""
    if not os.path.exists(MIGRATION_DIR):
        logger.error(f"迁移数据目录不存在: {MIGRATION_DIR}")
        logger.error("请先运行 migrate_data.py 导出数据")
        return

    registry = DatabaseRegistry(config.DATABASE_REGISTRY_FILE)
    service = RAGAnythingService(
        storage_root=config.RAGANYTHING_STORAGE_ROOT,
        output_root=config.RAGANYTHING_OUTPUT_ROOT,
        registry=registry,
    )

    total_success = 0
    total_fail = 0

    for db_id in _migration_database_ids(MIGRATION_DIR):
        json_file = os.path.join(MIGRATION_DIR, f"{db_id}.json")
        if not os.path.exists(json_file):
            logger.warning(f"跳过 {db_id}: 文件不存在")
            continue

        with open(json_file, 'r', encoding='utf-8') as f:
            documents = json.load(f)

        success, fail = await import_database(service, db_id, documents)
        total_success += success
        total_fail += fail

    logger.info(f"\n导入完成！总计: 成功 {total_success}, 失败 {total_fail}")


if __name__ == "__main__":
    asyncio.run(main())
