from __future__ import annotations

import re
from typing import Any


def _normalize_text(text: str) -> str:
    clean = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def chunk_text(
    text: str,
    source: str,
    database: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 120,
) -> list[dict[str, Any]]:
    clean = _normalize_text(text)
    if not clean:
        return []

    chunk_size = max(1, int(chunk_size))
    chunk_overlap = max(0, min(int(chunk_overlap), chunk_size // 2))
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 0

    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        if end < len(clean):
            boundary = max(clean.rfind("\n\n", start, end), clean.rfind("。", start, end), clean.rfind("\n", start, end))
            if boundary > start + chunk_size // 3:
                end = boundary + 1
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(
                {
                    "text": chunk,
                    "metadata": {
                        "source": source,
                        "database": database,
                        "chunk_index": index,
                        "start_char": start,
                        "end_char": end,
                    },
                }
            )
            index += 1
        if end >= len(clean):
            break
        start = max(0, end - chunk_overlap)

    return chunks
