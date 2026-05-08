"""
RAG-Anything API 启动脚本
自动选择可用 Python 运行时并启动服务
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path


os.chdir(os.path.dirname(os.path.abspath(__file__)))


def check_dependency(module_name: str, package_name: str | None = None) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        pkg = package_name or module_name
        print(f"[MISSING] {pkg} 未安装")
        return False


def _candidate_python() -> Path:
    env_python = os.getenv("RAGANYTHING_PYTHON", "").strip()
    if env_python:
        return Path(env_python)

    source_dir = os.getenv("RAGANYTHING_SOURCE_DIR", r"D:\GitHub_WorkSpace\RAG-Anything")
    return Path(source_dir) / ".venv" / "Scripts" / "python.exe"


def _need_reexec() -> bool:
    # raganything 官方依赖当前对 Python 3.14 不兼容，优先切到 3.12/3.13
    return sys.version_info >= (3, 14)


def _reexec_if_needed() -> None:
    if os.getenv("RAGANYTHING_START_REEXEC") == "1":
        return
    if not _need_reexec():
        return

    target = _candidate_python()
    if not target.exists():
        print(f"[WARN] 当前 Python {sys.version.split()[0]} 可能无法运行 raganything，且未找到可切换解释器: {target}")
        return

    print(f"[INFO] 当前 Python {sys.version.split()[0]} 不兼容，切换到: {target}")
    env = os.environ.copy()
    env["RAGANYTHING_START_REEXEC"] = "1"
    result = subprocess.run([str(target), __file__], env=env, check=False)
    sys.exit(result.returncode)


def main() -> None:
    _reexec_if_needed()

    print("=" * 60)
    print("  RAG-Anything API 启动检查")
    print("=" * 60)
    print()

    deps = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("dotenv", "python-dotenv"),
        ("requests", "requests"),
        ("pydantic", "pydantic"),
    ]

    missing = []
    for module, package in deps:
        if not check_dependency(module, package):
            missing.append(package)

    rag_available = check_dependency("raganything", "raganything")
    if not rag_available:
        print("[WARN] raganything 未安装，RAG 引擎将不可用")
        print(r"[WARN] 建议运行: python -m pip install -e D:\GitHub_WorkSpace\RAG-Anything")

    mineru_available = check_dependency("magic_pdf", "mineru[core]")
    if not mineru_available:
        print('[WARN] mineru[core] 未安装，文档解析能力将不可用')
        print('[WARN] 建议运行: python -m pip install -U "mineru[core]"')

    if missing:
        print()
        print(f"[ERROR] 缺少依赖: {', '.join(missing)}")
        print(f"请运行: python -m pip install {' '.join(missing)}")
        sys.exit(1)

    if not os.path.exists(".env"):
        print("[WARN] .env 文件不存在，请复制 .env.example 并填写 API 密钥")
        sys.exit(1)

    print("[OK] 依赖检查通过")
    print(f"[INFO] Python: {sys.executable}")
    print()
    print("正在启动 RAG-Anything API 服务...")
    print()

    import uvicorn
    import config

    uvicorn.run(
        "app:app",
        host=config.RAG_SERVICE_HOST,
        port=config.RAG_SERVICE_PORT,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
