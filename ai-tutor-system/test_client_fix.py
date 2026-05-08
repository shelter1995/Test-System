"""
验证MiniMax客户端修复
"""

import sys
import os
from pathlib import Path
sys.path.append('.')

from minimax_client import MiniMaxClient
import json

# 从.env加载配置
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# API配置
API_KEY = os.getenv("MINIMAX_API_KEY", "")
MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")

if not API_KEY:
    print("错误: 未找到MINIMAX_API_KEY配置")
    print("请在 ai-tutor-system/.env 中配置 MINIMAX_API_KEY")
    sys.exit(1)

def test_client():
    print("=" * 60)
    print("测试修复后的MiniMax客户端")
    print("=" * 60)

    # 创建客户端
    client = MiniMaxClient(api_key=API_KEY, model=MODEL)

    # 准备消息
    messages = [
        {"role": "user", "content": "你好，请用一句话介绍自己"}
    ]

    print(f"\n发送请求...")
    print(f"消息: {json.dumps(messages, ensure_ascii=False)}")

    # 调用API
    result = client.chat_completion(messages=messages, temperature=0.8, max_tokens=200)

    print(f"\n结果:")
    print(f"success: {result['success']}")

    if result['success']:
        print(f"\n✅ 成功!")
        print(f"内容: {result['content']}")
    else:
        print(f"\n❌ 失败!")
        print(f"错误: {result.get('error', 'Unknown error')}")

    print("=" * 60)

if __name__ == "__main__":
    test_client()
