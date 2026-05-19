from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ModelEndpoint:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout: int = 60

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def build_embedding_payload(endpoint: ModelEndpoint, texts: list[str]) -> dict[str, Any]:
    return {"model": endpoint.model, "input": texts}


def build_rerank_payload(endpoint: ModelEndpoint, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
    return {
        "model": endpoint.model,
        "query": query,
        "documents": documents,
        "top_n": max(1, int(top_n)),
        "return_documents": False,
    }


def build_chat_payload(endpoint: ModelEndpoint, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return {
        "model": endpoint.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }


class OpenAICompatibleClient:
    def __init__(self, endpoint: ModelEndpoint):
        self.endpoint = endpoint

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.endpoint.api_key}",
            "Content-Type": "application/json",
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            resp = await client.post(
                f"{self.endpoint.normalized_base_url}/embeddings",
                headers=self._headers(),
                json=build_embedding_payload(self.endpoint, texts),
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") or []
        items.sort(key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        if not documents:
            return []
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            resp = await client.post(
                f"{self.endpoint.normalized_base_url}/rerank",
                headers=self._headers(),
                json=build_rerank_payload(self.endpoint, query, documents, top_n),
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("results") or []

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            resp = await client.post(
                f"{self.endpoint.normalized_base_url}/chat/completions",
                headers=self._headers(),
                json=build_chat_payload(self.endpoint, system_prompt, user_prompt),
            )
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content") or "").strip()
