"""
统一 LLM 客户端。

8002 不直接读取本地 LLM 环境变量，而是通过 8003 的 LLM 代理接口使用前端模型设置。
"""

import json
import logging
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)


class UnifiedLLMClient:
    def __init__(self, base_url: str, timeout: int = 300):
        self.base_url = str(base_url or "http://localhost:8003").rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._model_info: dict[str, Any] | None = None

    def _settings(self, force_refresh: bool = False) -> dict[str, Any]:
        if self._model_info is not None and not force_refresh:
            return self._model_info
        response = self._session.get(f"{self.base_url}/settings/models", timeout=min(self.timeout, 10))
        response.raise_for_status()
        data = response.json()
        llm = data.get("llm") if isinstance(data, dict) else {}
        self._model_info = llm if isinstance(llm, dict) else {}
        return self._model_info

    def model_info(self, refresh: bool = False) -> dict[str, Any]:
        return dict(self._settings(force_refresh=refresh))

    @property
    def model(self) -> str:
        try:
            return str(self._settings().get("model") or "")
        except Exception:
            return ""

    @property
    def provider(self) -> str:
        try:
            return str(self._settings().get("provider") or "unified")
        except Exception:
            return "unified"

    def available(self) -> bool:
        try:
            settings = self._settings()
            return bool(settings.get("has_api_key"))
        except Exception as exc:
            logger.debug("统一 LLM 设置暂不可用: %s", exc)
            return False

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 16000,
    ) -> Dict[str, Any]:
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = self._session.post(f"{self.base_url}/llm/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                self._model_info = {
                    "provider": data.get("provider") or self.provider,
                    "model": data.get("model") or self.model,
                    "has_api_key": True,
                }
                return {"success": True, "content": str(data.get("content") or ""), "raw_response": data}
            return {
                "success": False,
                "error": str(data.get("error") or "统一 LLM 调用失败"),
                "error_type": "llm_proxy_error",
                "raw_response": data,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc), "error_type": "llm_proxy_unavailable"}

    def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 800,
    ):
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = self._session.post(
            f"{self.base_url}/llm/chat/stream",
            json=payload,
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:].strip()
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                logger.warning("统一 LLM 流式响应解析失败: %s", chunk[:100])
                continue
            if "delta" in data:
                yield str(data.get("delta") or "")
            elif data.get("code"):
                raise RuntimeError(str(data.get("message") or "统一 LLM 流式调用失败"))


def create_unified_llm_client(timeout: int = 300) -> UnifiedLLMClient:
    import tutor_config as config

    return UnifiedLLMClient(base_url=getattr(config, "RAG_SERVICE_URL", "http://localhost:8003"), timeout=timeout)
