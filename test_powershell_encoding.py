#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PowerShell终端中文显示
"""

import sys
import io
import os

# 测试不同的输出方法
print("=== 测试PowerShell终端中文显示 ===")

# 测试1: 直接打印中文
print("测试1: 直接打印中文")
print("你好，世界！这是中文测试。")
print("商务视频彩铃解决方案")

# 测试2: 使用sys.stdout直接输出
print("\n测试2: 使用sys.stdout直接输出")
sys.stdout.write("使用sys.stdout输出中文: 你好，世界！\n")
sys.stdout.flush()

# 测试3: 使用print函数的encoding参数（Python 3.7+）
print("\n测试3: 使用print函数")
print("中文测试: 测试中文显示", flush=True)

# 测试4: 测试JSON输出
print("\n测试4: 测试JSON输出")
import json
test_data = {
    "中文键": "中文值",
    "数据库": "商务视频彩铃数据库",
    "描述": "这是一个中文测试"
}
json_str = json.dumps(test_data, ensure_ascii=False)
print(f"JSON输出: {json_str}")

# 测试5: 检查终端编码
print("\n测试5: 检查终端编码")
print(f"sys.stdout.encoding: {sys.stdout.encoding}")
print(f"sys.stderr.encoding: {sys.stderr.encoding}")

# 测试6: 尝试设置终端编码
print("\n测试6: 尝试设置UTF-8编码")
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        print("已重新配置终端编码为UTF-8")
        print("重新测试中文输出: 你好，世界！")
    else:
        print("Python版本不支持reconfigure方法")
except Exception as e:
    print(f"设置编码失败: {e}")

# 测试7: 测试环境变量
print("\n测试7: 检查环境变量")
if 'PYTHONIOENCODING' in os.environ:
    print(f"PYTHONIOENCODING: {os.environ['PYTHONIOENCODING']}")
else:
    print("PYTHONIOENCODING环境变量未设置")

# 测试8: 测试文件系统编码
print("\n测试8: 检查文件系统编码")
print(f"sys.getfilesystemencoding(): {sys.getfilesystemencoding()}")
