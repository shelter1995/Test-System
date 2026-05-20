from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass
class RetrievalConfig:
    min_score: float = 0.25
    candidates: int = 20
    final_contexts: int = 8
    rewrite_enabled: bool = True
    max_rewrite_queries: int = 3


def build_rewrite_queries(query: str, rewrite_enabled: bool, max_rewrite_queries: int) -> list[str]:
    raw = str(query or "").strip()
    if not raw:
        return []
    if not rewrite_enabled:
        return [raw]

    limit = max(1, int(max_rewrite_queries or 1))
    queries = [raw]
    parts = [item.strip() for item in re.split(r"[,\.;:，。；：\n]+", raw) if item.strip()]
    for part in parts:
        if part not in queries:
            queries.append(part)
        if len(queries) >= limit:
            break
    return queries[:limit]


def _candidate_key(item: dict[str, Any]) -> tuple[str, int] | str:
    metadata = dict(item.get("metadata") or {})
    doc = str(item.get("document_sha256") or metadata.get("document_sha256") or "").strip()
    chunk = metadata.get("chunk_index")
    if doc and chunk is not None:
        return (doc, int(chunk))
    text = str(item.get("text") or "")
    source = str(metadata.get("source") or "")
    fallback = f"{source}\n{text}".encode("utf-8", errors="ignore")
    return sha256(fallback).hexdigest()


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[str, int] | str, dict[str, Any]] = {}
    best_order: list[tuple[str, int] | str] = []
    for item in candidates:
        key = _candidate_key(item)
        score = float(item.get("score") or 0.0)
        if key not in best_by_key:
            best_by_key[key] = dict(item)
            best_order.append(key)
            continue
        existing = best_by_key[key]
        existing_score = float(existing.get("score") or 0.0)
        if score > existing_score:
            best_by_key[key] = dict(item)
    deduped = [best_by_key[key] for key in best_order]
    deduped.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return deduped


def filter_candidates(candidates: list[dict[str, Any]], min_score: float) -> list[dict[str, Any]]:
    threshold = float(min_score)
    return [dict(item) for item in candidates if float(item.get("score") or 0.0) >= threshold]


def apply_rerank_order(candidates: list[dict[str, Any]], rerank_result: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates or not rerank_result:
        return [dict(item) for item in candidates]

    ordered: list[dict[str, Any]] = []
    used: set[int] = set()
    for item in rerank_result:
        index = int(item.get("index", -1))
        if index < 0 or index >= len(candidates) or index in used:
            continue
        enriched = dict(candidates[index])
        enriched["rerank_score"] = item.get("relevance_score")
        ordered.append(enriched)
        used.add(index)
    for index, item in enumerate(candidates):
        if index not in used:
            ordered.append(dict(item))
    return ordered


def assign_source_ids(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        enriched = dict(item)
        enriched["source_id"] = f"来源 {index}"
        assigned.append(enriched)
    return assigned
