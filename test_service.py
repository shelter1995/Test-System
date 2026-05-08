#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 RAG-Anything 服务健康状态。
"""

import requests

RAG_API = "http://localhost:8003"


def test_service_health():
    response = requests.get(f"{RAG_API}/status", timeout=20)
    print(f"状态码: {response.status_code}")
    print(f"响应内容: {response.json()}")
    return response.ok


def test_root_endpoint():
    response = requests.get(f"{RAG_API}/", timeout=20)
    print(f"根路径状态码: {response.status_code}")
    print(f"根路径响应: {response.json()}")
    return response.ok


if __name__ == "__main__":
    print("测试服务健康状态...")
    test_service_health()
    print("\n测试根路径...")
    test_root_endpoint()
