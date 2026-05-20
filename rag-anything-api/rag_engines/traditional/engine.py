from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rag_engines.contracts import ContextResult, IngestResult, SearchResult

from .chunking import chunk_text
from .document_loader import load_document_text
from .vector_store import TraditionalVectorStore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TraditionalRAGEngine:
    name = "traditional"

    def __init__(
        self,
        storage_root: str | Path,
        embedding_client: Any,
        rerank_client: Any | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 120,
    ):
        self.storage_root = Path(storage_root)
        self.embedding_client = embedding_client
        self.rerank_client = rerank_client
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _store(self, database_id: str) -> TraditionalVectorStore:
        return TraditionalVectorStore(self.storage_root / database_id / "traditional.sqlite")

    def _embedding_model_name(self) -> str:
        endpoint = getattr(self.embedding_client, "endpoint", None)
        return str(getattr(endpoint, "model", "") or "")

    def _rerank_model_name(self) -> str:
        endpoint = getattr(self.rerank_client, "endpoint", None)
        return str(getattr(endpoint, "model", "") or "")

    async def ingest_file(self, database_id: str, file_path: str | Path, source: str | None = None) -> dict[str, Any]:
        path = Path(file_path)
        loaded = load_document_text(path)
        document_sha256 = _sha256(path)
        source_name = source or loaded.metadata["file_name"]
        chunks = chunk_text(
            loaded.text,
            source=source_name,
            database=database_id,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        if not chunks:
            result = IngestResult(
                status="error",
                database=database_id,
                document_sha256=document_sha256,
                file_name=path.name,
                engine=self.name,
                chunk_count=0,
                message="文档没有可索引文本",
                error="empty_text",
            )
            return result.to_dict()

        embeddings = await self.embedding_client.embed([chunk["text"] for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise RuntimeError(f"Embedding 返回数量不匹配：期望 {len(chunks)}，实际 {len(embeddings)}")
        indexed = []
        for chunk, embedding in zip(chunks, embeddings):
            indexed.append({**chunk, "embedding": embedding})
        inserted = self._store(database_id).upsert_chunks(database_id, document_sha256, indexed)

        result = IngestResult(
            status="success",
            database=database_id,
            document_sha256=document_sha256,
            file_name=path.name,
            engine=self.name,
            chunk_count=inserted,
            message="文档已通过传统 RAG 导入知识库",
        ).to_dict()
        result["embedding_model"] = self._embedding_model_name()
        result["rerank_model"] = self._rerank_model_name()
        return result

    async def ingest_text(self, database_id: str, text: str, source: str = "manual") -> dict[str, Any]:
        text_dir = self.storage_root / database_id / "text_ingest"
        text_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(f"{source}\n{text}".encode("utf-8")).hexdigest()
        path = text_dir / f"{digest[:16]}.md"
        path.write_text(str(text or ""), encoding="utf-8")
        return await self.ingest_file(database_id, path, source=source)

    async def query(
        self,
        database_id: str,
        query: str,
        mode: str = "hybrid",
        n_results: int = 10,
        enable_rerank: bool | None = None,
        vlm_enhanced: bool | None = None,
    ) -> dict[str, Any]:
        embeddings = await self.embedding_client.embed([query])
        results = self._store(database_id).search(database_id, embeddings[0], top_k=max(1, int(n_results)))
        if enable_rerank and self.rerank_client and results:
            docs = [item["text"] for item in results]
            reranked = await self.rerank_client.rerank(query, docs, top_n=len(results))
            if reranked:
                ordered = []
                for item in reranked:
                    index = int(item.get("index", 0))
                    if 0 <= index < len(results):
                        copy = dict(results[index])
                        copy["rerank_score"] = item.get("relevance_score")
                        ordered.append(copy)
                results = ordered or results
        return SearchResult(query=query, database=database_id, results=results).to_dict()

    async def query_context(
        self,
        database_id: str,
        query: str,
        mode: str = "naive",
        max_chars: int = 3000,
    ) -> dict[str, Any]:
        result = await self.query(database_id, query, n_results=5, enable_rerank=True)
        contexts = []
        remaining = max(0, int(max_chars))
        for item in result.get("results", []):
            text = str(item.get("text") or "")
            if remaining and len(text) > remaining:
                text = text[:remaining]
            if text:
                enriched = {**item, "text": text}
                meta = dict(enriched.get("metadata") or {})
                meta.setdefault("engine", self.name)
                enriched["metadata"] = meta
                contexts.append(enriched)
                remaining -= len(text)
            if remaining <= 0:
                break
        return ContextResult(query=query, database=database_id, contexts=contexts).to_dict()

    async def delete_document(self, database_id: str, sha256: str) -> dict[str, Any]:
        deleted = self._store(database_id).delete_document(database_id, sha256)
        return {"status": "success", "database": database_id, "deleted_chunks": deleted}
