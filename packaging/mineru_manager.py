from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, MutableMapping


EXPECTED_MINERU_VERSION = "3.3.1"
CONFIG_MODEL_FILENAMES = {"mineru.json", ".gitkeep"}


class MineruPaths:
    def __init__(self, package_root: str | Path, data_root: str | Path) -> None:
        self.package_root = Path(package_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.package_runtime = self.package_root / "runtime"
        self.data_runtime = self.data_root / "runtime"
        self.python_exe = self.package_runtime / "python" / "python.exe"
        self.package_site_packages = self.package_runtime / "site-packages"
        self.rag_source = self.package_root / "rag-anything-api"
        self.requirements = self.package_root / "packaging" / "mineru-requirements.txt"
        self.current_target = self.data_runtime / "optional-site-packages"
        self.installing_target = self.data_runtime / "optional-site-packages.installing"
        self.previous_target = self.data_runtime / "optional-site-packages.previous"
        self.models_root = self.data_root / "models" / "mineru"
        self.lock_path = self.data_runtime / "mineru-install.lock"


class InstallLock:
    def __init__(self, path: Path, handle: int) -> None:
        self.path = path
        self.handle = handle
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        os.close(self.handle)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self._released = True

    def __enter__(self) -> "InstallLock":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def acquire_install_lock(paths: MineruPaths) -> InstallLock:
    paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        handle = os.open(paths.lock_path, flags)
    except FileExistsError:
        if _lock_is_stale(paths.lock_path):
            paths.lock_path.unlink(missing_ok=True)
            handle = os.open(paths.lock_path, flags)
        else:
            raise
    os.write(handle, str(os.getpid()).encode("ascii", errors="ignore"))
    return InstallLock(paths.lock_path, handle)


def _lock_is_stale(path: Path) -> bool:
    try:
        raw = path.read_text(encoding="ascii").strip()
        pid = int(raw)
    except (OSError, ValueError):
        return True
    return not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def build_pip_install_command(paths: MineruPaths) -> list[str]:
    return [
        str(paths.python_exe),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--target",
        str(paths.installing_target),
        "--requirement",
        str(paths.requirements),
    ]


def build_model_download_command(paths: MineruPaths, source: str) -> list[str]:
    return [
        str(paths.python_exe),
        "-m",
        "mineru.cli.models_download",
        "--source",
        source,
        "--model_type",
        "pipeline",
    ]


def build_install_environment(
    paths: MineruPaths,
    *,
    use_installing: bool,
    base_env: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    pythonpath_entries = []
    if use_installing:
        pythonpath_entries.append(str(paths.installing_target))
    else:
        pythonpath_entries.append(str(paths.current_target))
    pythonpath_entries.append(str(paths.rag_source))
    blocked_pythonpath_roots = {
        paths.current_target.resolve(),
        paths.installing_target.resolve(),
        paths.package_site_packages.resolve(),
    }
    existing_pythonpath = [
        item
        for item in env.get("PYTHONPATH", "").split(os.pathsep)
        if item and not _path_matches_any_root(Path(item), blocked_pythonpath_roots)
    ]
    env["PYTHONPATH"] = os.pathsep.join([*pythonpath_entries, *existing_pythonpath])

    existing_path = [item for item in env.get("PATH", "").split(os.pathsep) if item]
    env["PATH"] = os.pathsep.join([str(paths.python_exe.parent), *existing_path])
    env["PYTHONUTF8"] = "1"
    env["HF_HOME"] = str(paths.models_root / "huggingface")
    env["HUGGINGFACE_HUB_CACHE"] = str(paths.models_root / "huggingface" / "hub")
    env["MODELSCOPE_CACHE"] = str(paths.models_root / "modelscope")
    env["MINERU_TOOLS_CONFIG_JSON"] = str(paths.models_root / "mineru.json")
    return env


def _path_matches_any_root(path: Path, roots: set[Path]) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    return any(resolved == root or resolved.is_relative_to(root) for root in roots)


def _models_ready(models_root: Path) -> bool:
    if not models_root.exists():
        return False
    return any(
        path.is_file() and path.name not in CONFIG_MODEL_FILENAMES
        for path in models_root.rglob("*")
    )


def verify_installation(
    paths: MineruPaths,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    env = build_install_environment(paths, use_installing=True)
    verification = run(
        [
            str(paths.python_exe),
            "-c",
            (
                "import importlib.metadata as md\n"
                "from mineru.cli.client import main\n"
                "assert callable(main)\n"
                "print(md.version('mineru'))\n"
                "print('client-main-ok')\n"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if verification.returncode != 0:
        return False
    lines = [line.strip() for line in (verification.stdout or "").splitlines() if line.strip()]
    if not lines or lines[0] != EXPECTED_MINERU_VERSION:
        return False
    if "client-main-ok" not in lines:
        return False

    help_result = run(
        [str(paths.python_exe), "-m", "mineru.cli.models_download", "--help"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if help_result.returncode != 0 or not _models_ready(paths.models_root):
        return False

    media_result = run(
        [
            str(paths.python_exe),
            "-c",
            (
                "import imageio_ffmpeg\n"
                "import whisper\n"
                "ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()\n"
                "assert ffmpeg\n"
                "print('media-deps-ok')\n"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return media_result.returncode == 0 and "media-deps-ok" in (media_result.stdout or "")


def _write_status(path: str | Path, payload: dict[str, object]) -> None:
    status_path = Path(path)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _progress_record(stage: str, percent: int, message: str) -> dict[str, object]:
    return {"stage": stage, "percent": percent, "message": message}


def _json_progress(record: dict[str, object]) -> None:
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _failure(
    *,
    stage: str,
    message: str,
    status_json: str | Path,
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "error",
        "stage": stage,
        "message": message,
    }
    if returncode is not None:
        result["returncode"] = returncode
    if stdout:
        result["stdout"] = stdout
    if stderr:
        result["stderr"] = stderr
    _write_status(status_json, result)
    return result


def _prepare_directories(paths: MineruPaths) -> None:
    for directory in (
        paths.data_runtime,
        paths.current_target,
        paths.models_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def _promote_installing_target(paths: MineruPaths) -> None:
    shutil.rmtree(paths.previous_target, ignore_errors=True)
    if paths.current_target.exists():
        paths.current_target.replace(paths.previous_target)
    paths.installing_target.replace(paths.current_target)
    shutil.rmtree(paths.previous_target, ignore_errors=True)


def install_mineru(
    package_root: str | Path,
    data_root: str | Path,
    *,
    source: str,
    status_json: str | Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    verify: Callable[..., bool] = verify_installation,
    emit_progress: Callable[[dict[str, object]], None] = _json_progress,
) -> dict[str, object]:
    paths = MineruPaths(package_root, data_root)
    try:
        lock = acquire_install_lock(paths)
    except FileExistsError:
        return _failure(
            stage="lock",
            message="已有安装任务正在运行，请稍后再试",
            status_json=status_json,
        )

    with lock:
        _prepare_directories(paths)
        if not paths.python_exe.exists():
            return _failure(
                stage="python",
                message=f"缺少内置 Python: {paths.python_exe}",
                status_json=status_json,
            )
        if not paths.requirements.exists():
            return _failure(
                stage="requirements",
                message=f"缺少 MinerU 依赖文件: {paths.requirements}",
                status_json=status_json,
            )

        shutil.rmtree(paths.installing_target, ignore_errors=True)
        paths.installing_target.mkdir(parents=True, exist_ok=True)
        env = build_install_environment(paths, use_installing=True)

        emit_progress(_progress_record("dependencies", 10, "正在安装增强解析依赖（MinerU / FFmpeg / Whisper）"))
        pip_command = build_pip_install_command(paths)
        pip_result = run(pip_command, capture_output=True, text=True, check=False, env=env)
        if pip_result.returncode != 0:
            shutil.rmtree(paths.installing_target, ignore_errors=True)
            return _failure(
                stage="pip",
                message="增强解析依赖安装失败",
                status_json=status_json,
                returncode=pip_result.returncode,
                stdout=pip_result.stdout or "",
                stderr=pip_result.stderr or "",
            )

        emit_progress(_progress_record("models", 60, "正在下载 MinerU 模型"))
        model_command = build_model_download_command(paths, source)
        model_result = run(model_command, capture_output=True, text=True, check=False, env=env)
        if model_result.returncode != 0:
            shutil.rmtree(paths.installing_target, ignore_errors=True)
            return _failure(
                stage="models",
                message="MinerU 模型下载失败",
                status_json=status_json,
                returncode=model_result.returncode,
                stdout=model_result.stdout or "",
                stderr=model_result.stderr or "",
            )

        if not verify(paths, run=run):
            shutil.rmtree(paths.installing_target, ignore_errors=True)
            return _failure(
                stage="verify",
                message="MinerU 安装后验证失败",
                status_json=status_json,
            )

        _promote_installing_target(paths)
        result: dict[str, object] = {
            "status": "success",
            "stage": "complete",
            "message": "增强解析组件安装完成（MinerU / FFmpeg / Whisper）",
            "optional_site_packages": str(paths.current_target),
            "models": str(paths.models_root),
        }
        _write_status(status_json, result)
        emit_progress(_progress_record("complete", 100, "增强解析组件安装完成（MinerU / FFmpeg / Whisper）"))
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install and verify optional MinerU runtime components.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install")
    install.add_argument("--package-root", required=True)
    install.add_argument("--data-root", required=True)
    install.add_argument("--source", default="modelscope")
    install.add_argument("--status-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "install":
        result = install_mineru(
            args.package_root,
            args.data_root,
            source=args.source,
            status_json=args.status_json,
            emit_progress=_json_progress,
        )
        return 0 if result.get("status") == "success" else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
