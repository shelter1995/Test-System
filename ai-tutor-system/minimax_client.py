"""
MiniMax AI 客户端 — 支持超时、重试、指数退避
"""

import time
import logging
import requests
import json
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class MiniMaxClient:
    """MiniMax AI 客户端"""

    def __init__(self, api_key: str, model: str = "MiniMax-M2.7", timeout: int = 300, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.minimax.chat/v1"
        self.api_host = "api.minimax.chat"
        self.timeout = timeout
        self.max_retries = max_retries

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 16000
    ) -> Dict[str, Any]:
        """
        调用MiniMax聊天完成接口（带重试）

        Returns:
            {"success": True, "content": "...", "raw_response": ...} 或
            {"success": False, "error": "...", "error_type": "timeout"|"server_error"|...}
        """
        url = f"{self.base_url}/text/chatcompletion_v2"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()

                base_resp = result.get("base_resp", {})
                status_code = base_resp.get("status_code", 0)
                if status_code != 0:
                    err_msg = f"MiniMax API 业务错误 [{status_code}]: {base_resp.get('status_msg', '未知错误')}"
                    return {"success": False, "error": err_msg, "error_type": "business_error", "raw_response": result}

                if "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0]
                    if "message" in choice:
                        content = choice["message"].get("content", "")
                    elif "messages" in choice and len(choice["messages"]) > 0:
                        content = choice["messages"][-1].get("text", "")
                    else:
                        content = ""

                    if not content or not content.strip():
                        return {"success": False, "error": "Empty response content from API", "error_type": "empty_response", "raw_response": result}

                    return {"success": True, "content": content, "raw_response": result}
                else:
                    return {"success": False, "error": "No response from API", "error_type": "no_choices", "raw_response": result}

            except requests.exceptions.Timeout:
                last_error = f"MiniMax API 请求超时（{self.timeout}s）"
                logger.warning(f"{last_error} (尝试 {attempt + 1}/{self.max_retries + 1})")
            except requests.exceptions.ConnectionError as e:
                last_error = f"MiniMax API 连接失败: {e}"
                logger.warning(f"{last_error} (尝试 {attempt + 1}/{self.max_retries + 1})")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if hasattr(e, 'response') and e.response is not None else 0
                if status in (502, 503, 504):
                    last_error = f"MiniMax 服务器临时不可用 (HTTP {status})"
                    logger.warning(f"{last_error} (尝试 {attempt + 1}/{self.max_retries + 1})")
                elif status == 429:
                    last_error = "MiniMax API 速率限制 (429)"
                    logger.warning(f"{last_error} (尝试 {attempt + 1}/{self.max_retries + 1})")
                else:
                    raise

            if attempt < self.max_retries:
                backoff = 2 ** attempt
                time.sleep(backoff)

        return {"success": False, "error": last_error or "未知错误", "error_type": "retry_exhausted"}

    def create_completion(self, prompt: str, temperature: float = 0.8, max_tokens: int = 16000) -> str:
        """
        简单的补全接口

        Args:
            prompt: 提示文本
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        result = self.chat_completion(messages, temperature, max_tokens)

        if result["success"]:
            return result["content"]
        else:
            raise Exception(f"MiniMax API调用失败: {result.get('error', 'Unknown error')}")


def create_minimax_client(api_key: str, model: str = "MiniMax-M2.7") -> MiniMaxClient:
    """
    创建MiniMax客户端的工厂函数

    Args:
        api_key: API密钥
        model: 模型名称

    Returns:
        MiniMaxClient实例
    """
    return MiniMaxClient(api_key=api_key, model=model)
