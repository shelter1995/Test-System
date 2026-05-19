from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class IngestResult:
    status: str
    database: str
    document_sha256: str
    file_name: str
    engine: str
    chunk_count: int
    message: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "database": self.database,
            "document_sha256": self.document_sha256,
            "file_name": self.file_name,
            "engine": self.engine,
            "chunk_count": self.chunk_count,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class SearchResult:
    query: str
    database: str
    results: list[dict[str, Any]] = field(default_factory=list)
    fallback: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "query": self.query,
            "database": self.database,
            "results": self.results,
            "total_found": len(self.results),
        }
        if self.fallback:
            payload["fallback"] = self.fallback
        return payload


@dataclass
class ContextResult:
    query: str
    database: str
    contexts: list[dict[str, Any]] = field(default_factory=list)
    fallback: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "query": self.query,
            "database": self.database,
            "contexts": self.contexts,
            "total_found": len(self.contexts),
        }
        if self.fallback:
            payload["fallback"] = self.fallback
        return payload


class RAGEngine(Protocol):
    name: str

    async def ingest_file(self, database_id: str, file_path: str | Path, source: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def ingest_text(self, database_id: str, text: str, source: str = "manual") -> dict[str, Any]:
        raise NotImplementedError

    async def query(
        self,
        database_id: str,
        query: str,
        mode: str = "hybrid",
        n_results: int = 10,
        enable_rerank: bool | None = None,
        vlm_enhanced: bool | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def query_context(
        self,
        database_id: str,
        query: str,
        mode: str = "naive",
        max_chars: int = 3000,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def delete_document(self, database_id: str, sha256: str) -> dict[str, Any]:
        raise NotImplementedError
