import requests

RAG_API = "http://localhost:8003"

response = requests.post(
    f"{RAG_API}/ai_enhanced_search",
    json={
        "query": "商务视频彩铃 一部一案 资费价格 定价标准",
        "database": "商务彩铃",
        "n_results": 50,
    },
    timeout=180,
)
response.raise_for_status()

data = response.json()
print(f"Total results: {len(data.get('results', []))}")
print("\n搜索查询扩展：")
for q in data.get("enhanced_queries", []):
    print(f"- {q}")

print("\n结果详情：")
for i, result in enumerate(data.get("results", [])):
    source = result.get("metadata", {}).get("source", "未知")
    text = result.get("text", "")
    text = text[:200] + "..." if len(text) > 200 else text
    score = result.get("score", 0)
    print(f"\n{i + 1}. 来源: {source} (相似度: {score:.4f})")
    print(f"内容: {text}")
