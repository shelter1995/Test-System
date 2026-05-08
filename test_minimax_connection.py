"""
测试MiniMax API连接
"""
import requests
import sys
import io
import os

# 设置UTF-8编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 从ai-tutor-system/.env加载配置
env_path = os.path.join(os.path.dirname(__file__), "ai-tutor-system", ".env")
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

API_KEY = os.getenv("MINIMAX_API_KEY", "")

if not API_KEY:
    print("错误: 未找到MINIMAX_API_KEY配置")
    print("请在 ai-tutor-system/.env 中配置 MINIMAX_API_KEY")
    sys.exit(1)

print("测试MiniMax API连接...")
print(f"API Key: {API_KEY[:20]}...")

url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

data = {
    "model": "MiniMax-2.7",
    "messages": [
        {"role": "user", "content": "你好，请简单介绍一下自己"}
    ],
    "temperature": 0.8,
    "max_tokens": 100
}

try:
    print("发送请求中（超时120秒）...")
    response = requests.post(url, headers=headers, json=data, timeout=120)
    print(f"状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("API调用成功!")
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            print(f"回复: {content[:200]}")
    else:
        print(f"请求失败: {response.status_code}")
        print(response.text)

except Exception as e:
    print(f"发生错误: {e}")

print("\n测试完成")
