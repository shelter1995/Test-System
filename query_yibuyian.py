import requests

RAG_API = "http://localhost:8003"

response = requests.post(
    f"{RAG_API}/ai_enhanced_search",
    json={
        "query": "一部一案",
        "database": "商务彩铃",
        "n_results": 50,
    },
    timeout=180,
)
response.raise_for_status()

data = response.json()
print(f"Total results: {len(data.get('results', []))}")
print("\n相关文档来源：")
for result in data.get("results", []):
    source = result.get("metadata", {}).get("source", "未知")
    print(f"- {source}")

print("\n搜索查询扩展：")
for q in data.get("enhanced_queries", []):
    print(f"- {q}")
