#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目打包脚本
将整个AI话术陪练系统项目打包成一个完整的分发包
"""

import os
import shutil
import zipfile
import datetime
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "dist"

def create_distribution():
    """创建项目分发包"""
    print("🚀 开始打包项目...")
    
    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 生成打包文件名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    package_name = f"ai-tutor-system_{timestamp}.zip"
    package_path = OUTPUT_DIR / package_name
    
    # 需要包含的目录和文件
    include_patterns = [
        "ai-tutor-system/",
        "rag-anything-api/",
        "peixun-skill/",
        "solution-generator-skill/",
        "*.py",
        "*.md",
        "*.txt",
        "*.json",
        "*.bat",
        ".gitignore"
    ]
    
    # 需要排除的目录和文件
    exclude_patterns = [
        "__pycache__/",
        "venv/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.egg-info/",
        "build/",
        "dist/",
        ".git/",
        ".claude/",
        "*.log",
        ".env",
        "*.swp",
        "*.swo",
        "*~",
        "Thumbs.db",
        ".DS_Store"
    ]
    
    # 收集所有要打包的文件
    files_to_package = []
    
    def should_exclude_path(path):
        """检查路径是否应该排除"""
        for exclude_pattern in exclude_patterns:
            if exclude_pattern.endswith('/'):
                # 排除目录
                if str(path).startswith(str(PROJECT_ROOT / exclude_pattern[:-1])):
                    return True
            else:
                # 排除文件
                if path.name == exclude_pattern or exclude_pattern in str(path):
                    return True
        return False
    
    # 递归收集文件
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 过滤目录
        dirs[:] = [d for d in dirs if not should_exclude_path(Path(root) / d)]
        
        # 收集文件
        for file in files:
            file_path = Path(root) / file
            
            # 检查文件是否应该包含
            should_include = False
            
            # 检查是否匹配包含模式
            for pattern in include_patterns:
                if pattern.endswith('/'):
                    # 目录模式
                    if str(file_path).startswith(str(PROJECT_ROOT / pattern[:-1])):
                        should_include = True
                        break
                else:
                    # 文件模式
                    if file_path.match(pattern):
                        should_include = True
                        break
            
            # 如果应该包含且不应该排除
            if should_include and not should_exclude_path(file_path):
                files_to_package.append(file_path)
    
    print(f"📦 收集到 {len(files_to_package)} 个文件")
    
    # 创建ZIP文件
    with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files_to_package:
            # 计算相对路径
            rel_path = file_path.relative_to(PROJECT_ROOT)
            zipf.write(file_path, rel_path)
            print(f"   添加: {rel_path}")
    
    print(f"\n✅ 打包完成！")
    print(f"📁 包文件位置: {package_path}")
    print(f"📊 文件大小: {package_path.stat().st_size / 1024 / 1024:.2f} MB")
    
    return package_path

if __name__ == "__main__":
    create_distribution()
