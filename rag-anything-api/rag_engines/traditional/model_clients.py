from __future__ import annotations

import asyncio
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
    batch_size: int = 20
    batch_interval: float = 0.0
    retry_attempts: int = 3
    retry_base_delay: float = 30.0

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

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        base_delay = float(getattr(self.endpoint, "retry_base_delay", 30.0) or 30.0)
        return base_delay * (attempt + 1)

    async def _post_json(self, client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        max_retries = max(0, int(getattr(self.endpoint, "retry_attempts", 3) or 0))
        for attempt in range(max_retries + 1):
            resp = await client.post(url, headers=self._headers(), json=payload)
            try:
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(self._retry_delay(resp, attempt))
                    continue
                detail = resp.text[:1000]
                reason = getattr(exc.response, "reason_phrase", "") or "Error"
                raise RuntimeError(f"{exc.response.status_code} {reason}: {detail}") from exc
        raise RuntimeError("Request failed after retries")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batch_size = max(1, int(getattr(self.endpoint, "batch_size", 20) or 20))
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            starts = list(range(0, len(texts), batch_size))
            for index, start in enumerate(starts):
                batch = texts[start:start + batch_size]
                data = await self._post_json(
                    client,
                    f"{self.endpoint.normalized_base_url}/embeddings",
                    build_embedding_payload(self.endpoint, batch),
                )
                items = data.get("data") or []
                items.sort(key=lambda item: item.get("index", 0))
                vectors.extend(item["embedding"] for item in items)
                interval = float(getattr(self.endpoint, "batch_interval", 0.0) or 0.0)
                if interval > 0 and index < len(starts) - 1:
                    await asyncio.sleep(interval)
        return vectors

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        if not documents:
            return []
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            data = await self._post_json(
                client,
                f"{self.endpoint.normalized_base_url}/rerank",
                build_rerank_payload(self.endpoint, query, documents, top_n),
            )
        return data.get("results") or []

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
            data = await self._post_json(
                client,
                f"{self.endpoint.normalized_base_url}/chat/completions",
                build_chat_payload(self.endpoint, system_prompt, user_prompt),
            )
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content") or "").strip()
