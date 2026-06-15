from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, MutableMapping


BASE_MODULES = (
    "fastapi",
    "uvicorn",
    "dotenv",
    "httpx",
    "pydantic",
    "numpy",
    "pypdf",
    "docx",
    "openpyxl",
    "raganything",
    "openai",
)


def _paths(package_root: str | Path) -> dict[str, Path]:
    root = Path(package_root).resolve()
    runtime = root / "runtime"
    models = runtime / "models" / "mineru"
    return {
        "root": root,
        "runtime": runtime,
        "python": runtime / "python",
        "site_packages": runtime / "site-packages",
        "optional_site_packages": runtime / "optional-site-packages",
        "models": models,
        "logs": runtime / "logs",
        "requirements": root / "packaging" / "mineru-requirements.txt",
        "rag_source": root / "rag-anything-api",
    }


def configure_runtime_environment(
    package_root: str | Path,
    environ: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    paths = _paths(package_root)
    env = environ if environ is not None else os.environ
    for path in (
        paths["site_packages"],
        paths["optional_site_packages"],
        paths["models"],
        paths["logs"],
    ):
        path.mkdir(parents=True, exist_ok=True)

    existing_pythonpath = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(paths["optional_site_packages"]),
            str(paths["site_packages"]),
            str(paths["rag_source"]),
            *existing_pythonpath,
        ]
    )

    existing_path = [item for item in env.get("PATH", "").split(os.pathsep) if item]
    env["PATH"] = os.pathsep.join([str(paths["python"]), *existing_path])
    env["PYTHONUTF8"] = "1"
    env["HF_HOME"] = str(paths["models"] / "huggingface")
    env["HUGGINGFACE_HUB_CACHE"] = str(paths["models"] / "huggingface" / "hub")
    env["MODELSCOPE_CACHE"] = str(paths["models"] / "modelscope")
    env["MINERU_TOOLS_CONFIG_JSON"] = str(paths["models"] / "mineru.json")
    return env


def _can_import(name: str, importer: Callable[[str], object]) -> bool:
    try:
        importer(name)
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def _models_ready(models_dir: Path) -> bool:
    if not models_dir.exists():
        return False
    ignored = {"mineru.json", ".gitkeep"}
    return any(path.is_file() and path.name not in ignored for path in models_dir.rglob("*"))


def probe_runtime(
    package_root: str | Path,
    *,
    importer: Callable[[str], object] = importlib.import_module,
) -> dict[str, object]:
    paths = _paths(package_root)
    configure_runtime_environment(package_root)
    for site_dir in (paths["optional_site_packages"], paths["site_packages"], paths["rag_source"]):
        text = str(site_dir)
        if text not in sys.path:
            sys.path.insert(0, text)

    imports = {name: _can_import(name, importer) for name in BASE_MODULES}
    mineru_installed = _can_import("mineru", importer)
    mineru_cli = False
    if mineru_installed:
        try:
            client = importer("mineru.cli.client")
            mineru_cli = callable(getattr(client, "main", None))
        except (ImportError, ModuleNotFoundError):
            mineru_cli = False

    missing = [name for name, available in imports.items() if not available]
    return {
        "python_ready": Path(sys.executable).exists(),
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "base_dependencies_ready": not missing,
        "missing_base_modules": missing,
        "uvicorn_importable": imports["uvicorn"],
        "raganything_importable": imports["raganything"],
        "openai_importable": imports["openai"],
        "mineru_package_installed": mineru_installed,
        "mineru_cli_runnable": mineru_cli,
        "mineru_models_ready": _models_ready(paths["models"]),
    }


def build_mineru_install_command(requirements: Path, target: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--target",
        str(target),
        "--requirement",
        str(requirements),
    ]


def check_network(url: str = "https://pypi.org/simple/mineru/", timeout: int = 10) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(getattr(response, "status", 200)) < 400
    except OSError:
        return False


def check_url(url: str, timeout: int = 2) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(getattr(response, "status", 200)) < 500
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 500
    except OSError:
        return False


def _verify_mineru_target(target: Path) -> bool:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(target), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from mineru.cli.client import main; assert callable(main)",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return result.returncode == 0


def install_mineru(
    package_root: str | Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    network_check: Callable[[], bool] = check_network,
    verify: Callable[[Path], bool] = _verify_mineru_target,
) -> dict[str, object]:
    paths = _paths(package_root)
    configure_runtime_environment(package_root)
    requirements = paths["requirements"]
    target = paths["optional_site_packages"]
    installing = target.with_name(f"{target.name}.installing")
    backup = target.with_name(f"{target.name}.previous")
    log_path = paths["logs"] / "mineru-install.log"

    if not requirements.exists():
        return {"status": "error", "message": f"缺少 MinerU 依赖文件: {requirements}", "log": str(log_path)}
    if not network_check():
        return {"status": "error", "message": "无法连接依赖下载源，请检查网络后重试", "log": str(log_path)}

    shutil.rmtree(installing, ignore_errors=True)
    installing.mkdir(parents=True, exist_ok=True)
    command = build_mineru_install_command(requirements, installing)
    result = run(command, capture_output=True, text=True, check=False, env=dict(os.environ))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"$ {' '.join(command)}\n\nSTDOUT\n{result.stdout or ''}\n\nSTDERR\n{result.stderr or ''}\n",
        encoding="utf-8",
    )

    if result.returncode != 0:
        shutil.rmtree(installing, ignore_errors=True)
        return {"status": "error", "message": "MinerU 依赖安装失败", "log": str(log_path)}
    shutil.rmtree(installing / "bin", ignore_errors=True)
    if not verify(installing):
        shutil.rmtree(installing, ignore_errors=True)
        return {"status": "error", "message": "MinerU 安装后验证失败", "log": str(log_path)}

    shutil.rmtree(backup, ignore_errors=True)
    if target.exists():
        target.replace(backup)
    installing.replace(target)
    shutil.rmtree(backup, ignore_errors=True)
    return {"status": "success", "message": "MinerU 安装完成", "log": str(log_path)}


def write_check_outputs(
    result: dict[str, object],
    *,
    json_output: str | Path | None = None,
    cmd_output: str | Path | None = None,
) -> None:
    if json_output:
        json_path = Path(json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    if cmd_output:
        cmd_path = Path(cmd_output)
        cmd_path.parent.mkdir(parents=True, exist_ok=True)
        missing = ", ".join(str(item) for item in result.get("missing_base_modules", []))
        lines = (
            f'set "BASE_READY={int(bool(result.get("base_dependencies_ready")))}"',
            f'set "MINERU_READY={int(bool(result.get("mineru_cli_runnable")))}"',
            f'set "MISSING_BASE_MODULES={missing}"',
        )
        cmd_path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Test-System portable runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    check.add_argument("--json-output")
    check.add_argument("--cmd-output")
    install = subparsers.add_parser("install-mineru")
    install.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    url_check = subparsers.add_parser("check-url")
    url_check.add_argument("url")
    url_check.add_argument("--timeout", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check-url":
        return 0 if check_url(args.url, timeout=args.timeout) else 1
    if args.command == "check":
        result = probe_runtime(args.root)
        write_check_outputs(result, json_output=args.json_output, cmd_output=args.cmd_output)
    else:
        result = install_mineru(args.root)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
