import requests

RAG_API = "http://localhost:8003"

response = requests.post(
    f"{RAG_API}/ai_enhanced_search",
    json={
        "query": "一部一案对内.pptx 资费",
        "database": "商务彩铃",
        "n_results": 20,
    },
    timeout=180,
)
response.raise_for_status()

data = response.json()
print(f"Total results: {len(data.get('results', []))}")

print("\n一部一案相关内容：")
for result in data.get("results", []):
    source = result.get("metadata", {}).get("source", "未知")
    text = result.get("text", "")
    score = result.get("score", 0)
    print(f"\n来源: {source} (相似度: {score:.4f})")
    print(f"内容:\n{text}")
