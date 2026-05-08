#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询商务视频彩铃价格体系。

当前统一通过 RAG-Anything 服务查询，不再直接读取旧向量库。
"""

import requests

RAG_API = "http://localhost:8003"


def query_pricing_system():
    response = requests.post(
        f"{RAG_API}/ai_enhanced_search",
        json={
            "query": "商务视频彩铃价格体系 收费标准 价格方案",
            "database": "商务彩铃",
            "n_results": 15,
        },
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()

    print(f"\n找到 {len(data.get('results', []))} 条相关结果")
    print("=" * 80)
    for result in data.get("results", []):
        source = result.get("metadata", {}).get("source", "未知")
        print(f"\n来源: {source}")
        print(result.get("text", ""))
        print("-" * 40)


if __name__ == "__main__":
    query_pricing_system()
