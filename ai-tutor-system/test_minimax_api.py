"""
MiniMax API 测试脚本 - 简化版
"""

import requests
import json
import sys
import os
from pathlib import Path

# 设置输出编码
sys.stdout.reconfigure(encoding='utf-8')

# 从.env加载配置
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

API_KEY = os.getenv("MINIMAX_API_KEY", "")
MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
BASE_URL = "https://api.minimax.chat/v1"

if not API_KEY:
    print("错误: 未找到MINIMAX_API_KEY配置")
    print("请在 ai-tutor-system/.env 中配置 MINIMAX_API_KEY")
    sys.exit(1)

def test_chat_completion():
    """测试聊天完成接口"""
    url = f"{BASE_URL}/text/chatcompletion_v2"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "你好，请简单介绍一下你自己。"}
        ],
        "temperature": 0.8,
        "max_tokens": 800
    }

    print("测试MiniMax API调用...")
    print(f"URL: {url}")
    print(f"Model: {MODEL}")

    try:
        print("发送请求中 (可能需要几秒钟)...")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()

            # 保存到文件以便查看
            with open("minimax_response.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print("响应已保存到 minimax_response.json")

            print("\n响应结构分析:")
            print(f"Keys: {list(result.keys())}")

            if "choices" in result:
                print(f"\nChoices数量: {len(result['choices'])}")
                if len(result['choices']) > 0:
                    choice = result['choices'][0]
                    print(f"Choice Keys: {list(choice.keys())}")

                    # 检查不同格式
                    if "messages" in choice:
                        print("\n找到 'messages' 字段!")
                        print(f"Messages内容: {choice['messages']}")
                    elif "message" in choice:
                        print("\n找到 'message' 字段!")
                        print(f"Message内容: {choice['message']}")
                    else:
                        print(f"\nChoice内容: {choice}")

            return result
        else:
            print(f"请求失败: {response.status_code}")
            print(response.text)
            return None

    except requests.exceptions.Timeout:
        print("请求超时!")
        return None
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = test_chat_completion()
