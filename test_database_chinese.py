#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 RAG-Anything 数据库接口中文显示。
"""

import json
import requests

RAG_API = "http://localhost:8003"


def test_database_list():
    response = requests.get(f"{RAG_API}/db/list", timeout=20)
    print(f"状态码: {response.status_code}")
    print("原始响应:")
    print(response.text)
    print("\n解析后的数据:")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


def test_status_endpoint():
    response = requests.get(f"{RAG_API}/status", timeout=20)
    print(f"\n\n状态端点状态码: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    print("=== 测试数据库列表 ===")
    test_database_list()
    print("\n" + "=" * 50)
    print("=== 测试状态端点 ===")
    test_status_endpoint()
