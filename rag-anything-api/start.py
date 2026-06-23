"""
RAG-Anything API 启动脚本
自动检查依赖并启动服务
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))

python_scripts_dir = Path(sys.executable).parent
if python_scripts_dir.exists():
    entries = [item for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    if str(python_scripts_dir) not in entries:
        os.environ["PATH"] = os.pathsep.join([str(python_scripts_dir), *entries])


def check_dependency(module_name: str, package_name: str | None = None) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        pkg = package_name or module_name
        print(f"[MISSING] {pkg} 未安装")
        return False


def check_command(command: str, package_name: str | None = None) -> bool:
    try:
        subprocess.run(
            [command, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pkg = package_name or command
        print(f"[MISSING] {pkg} 未安装")
        return False


def main() -> None:
    print("=" * 60)
    print("  RAG-Anything API 启动检查")
    print("=" * 60)
    print()

    deps = [
        ("raganything", "raganything"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("dotenv", "python-dotenv"),
        ("httpx", "httpx"),
        ("pydantic", "pydantic"),
        ("numpy", "numpy"),
        ("pypdf", "pypdf"),
        ("docx", "python-docx"),
        ("openpyxl", "openpyxl"),
        ("openai", "openai"),
    ]

    missing = []
    for module, package in deps:
        if not check_dependency(module, package):
            missing.append(package)

    # 便携包通过包内 Python 模块调用 MinerU，不依赖可迁移性差的 console-script exe。
    mineru_ok = check_dependency("mineru", "mineru[core]") or check_command("mineru", "mineru[core]")
    if not mineru_ok:
        print('[WARN] mineru[core] 未安装，PDF/Office 文档解析不可用（文本导入正常）')
        print('[WARN] 如需解析文档: pip install -U "mineru[core]"')

    if missing:
        print()
        print(f"[ERROR] 缺少依赖: {', '.join(missing)}")
        print(f"请运行: pip install {' '.join(missing)}")
        sys.exit(1)

    if not Path(".env").exists():
        print("[WARN] .env 文件不存在，将使用环境变量或安装版数据目录中的配置")

    print("[OK] 依赖检查通过")
    print(f"[INFO] Python: {sys.version.split()[0]}")
    print()
    print("正在启动 RAG-Anything API 服务...")
    print()

    import uvicorn
    import config
    from app import app

    server_config = uvicorn.Config(
        app,
        host=config.RAG_SERVICE_HOST,
        port=config.RAG_SERVICE_PORT,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(server_config)
    app.state.uvicorn_server = server
    server.run()


if __name__ == "__main__":
    main()
