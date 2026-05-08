"""
MiniMax AI 客户端
"""

import requests
import json
from typing import List, Dict, Optional, Any


class MiniMaxClient:
    """MiniMax AI 客户端"""

    def __init__(self, api_key: str, model: str = "MiniMax-M2.7"):
        """
        初始化MiniMax客户端

        Args:
            api_key: MiniMax API密钥
            model: 模型名称，默认为 MiniMax-M2.7
        """
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.minimax.chat/v1"
        self.api_host = "api.minimax.chat"

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = 800
    ) -> Dict[str, Any]:
        """
        调用MiniMax聊天完成接口

        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成的token数

        Returns:
            API响应结果
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

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            response.raise_for_status()

            result = response.json()

            base_resp = result.get("base_resp", {})
            status_code = base_resp.get("status_code", 0)
            if status_code != 0:
                return {
                    "success": False,
                    "error": f"MiniMax API 业务错误 [{status_code}]: {base_resp.get('status_msg', '未知错误')}",
                    "raw_response": result
                }

            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]

                # MiniMax API返回格式: choice["message"]["content"]
                if "message" in choice:
                    content = choice["message"].get("content", "")
                elif "messages" in choice and len(choice["messages"]) > 0:
                    # 兼容其他可能的格式
                    content = choice["messages"][-1].get("text", "")
                else:
                    content = ""

                if not content or not content.strip():
                    return {
                        "success": False,
                        "error": "Empty response content from API",
                        "raw_response": result
                    }

                return {
                    "success": True,
                    "content": content,
                    "raw_response": result
                }
            else:
                return {
                    "success": False,
                    "error": "No response from API",
                    "raw_response": result
                }

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e)
            }

    def create_completion(self, prompt: str, temperature: float = 0.8, max_tokens: int = 800) -> str:
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
