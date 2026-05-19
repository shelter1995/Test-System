from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np


class TraditionalVectorStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    database TEXT NOT NULL,
                    document_sha256 TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_database ON chunks(database)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(database, document_sha256)")

    def upsert_chunks(self, database: str, document_sha256: str, chunks: list[dict[str, Any]]) -> int:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM chunks WHERE database = ? AND document_sha256 = ?",
                (database, document_sha256),
            )
            inserted = 0
            for chunk in chunks:
                embedding = np.asarray(chunk["embedding"], dtype=np.float32)
                metadata = dict(chunk.get("metadata") or {})
                chunk_index = int(metadata.get("chunk_index", inserted))
                conn.execute(
                    """
                    INSERT INTO chunks (
                        database, document_sha256, chunk_index, text, metadata_json, embedding, embedding_dim
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        database,
                        document_sha256,
                        chunk_index,
                        str(chunk.get("text") or ""),
                        json.dumps(metadata, ensure_ascii=False),
                        embedding.tobytes(),
                        int(embedding.shape[0]),
                    ),
                )
                inserted += 1
            return inserted

    def delete_document(self, database: str, document_sha256: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM chunks WHERE database = ? AND document_sha256 = ?",
                (database, document_sha256),
            )
            return int(cursor.rowcount or 0)

    def search(self, database: str, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        query = np.asarray(query_embedding, dtype=np.float32)
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0:
            return []

        rows = []
        with self._connect() as conn:
            for row in conn.execute("SELECT * FROM chunks WHERE database = ?", (database,)):
                vector = np.frombuffer(row["embedding"], dtype=np.float32)
                vector_norm = float(np.linalg.norm(vector))
                if vector_norm == 0:
                    continue
                score = float(np.dot(query, vector) / (query_norm * vector_norm))
                rows.append(
                    {
                        "text": row["text"],
                        "score": score,
                        "metadata": json.loads(row["metadata_json"]),
                        "document_sha256": row["document_sha256"],
                    }
                )
        rows.sort(key=lambda item: item["score"], reverse=True)
        return rows[: max(1, int(top_k))]
