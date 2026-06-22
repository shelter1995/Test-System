from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PACKAGE_NAME = "Test-System-Portable"
REQUIRED_PYTHON_VERSION = "3.13.10"
REQUIRED_PYTHON_MACHINE = "AMD64"
REQUIRED_PYTHON_BITS = "64bit"


@dataclass(frozen=True)
class PythonRuntimeInfo:
    version: str
    machine: str
    bits: str

INCLUDE_ITEMS = (
    "ai-tutor-system",
    "rag-anything-api",
    "assets",
    "docs",
    "packaging",
    "peixun-skill",
    "solution-generator-skill",
    "README.md",
    "SETUP.md",
    "CHANGELOG.md",
    "使用说明.md",
    "部署说明.md",
    "rag_database_guide.md",
    "start_services.bat",
    "install_mineru.bat",
)

EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist-portable",
    "generation_output",
    "outputs",
    "tmp",
    "tutor_data",
}


def should_exclude(relative_path: Path) -> bool:
    parts = tuple(part.replace("\\", "/") for part in relative_path.parts if part not in {"", "."})
    if not parts:
        return False
    if parts[-1] == ".env":
        return True
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    if len(parts) >= 2 and parts[0] == "rag-anything-api" and parts[1] in {"storage", "output"}:
        return True
    if len(parts) >= 3 and parts[:3] == ("runtime", "models", "mineru"):
        return True
    return False


def copy_filtered(source: Path, target: Path, root: Path) -> None:
    relative = source.relative_to(root)
    if should_exclude(relative):
        return
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            copy_filtered(child, target / child.name, root)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def normalize_batch_line_endings(package_dir: Path) -> None:
    for path in package_dir.rglob("*.bat"):
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        path.write_bytes(content.replace(b"\n", b"\r\n"))


def validate_python_runtime(
    python_home: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> PythonRuntimeInfo:
    python_exe = python_home / "python.exe"
    if not python_exe.exists():
        raise FileNotFoundError(f"Python executable not found: {python_exe}")
    result = run(
        [
            str(python_exe),
            "-c",
            (
                "import json, platform; "
                "print(json.dumps({'version': platform.python_version(), "
                "'machine': platform.machine(), 'bits': platform.architecture()[0]}))"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to execute portable Python: {result.stderr}")
    try:
        payload = json.loads((result.stdout or "").strip())
        info = PythonRuntimeInfo(
            version=str(payload["version"]),
            machine=str(payload["machine"]),
            bits=str(payload["bits"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Portable Python returned invalid runtime JSON: {result.stdout!r}") from exc

    normalized_machine = info.machine.upper()
    checks = (
        ("version", REQUIRED_PYTHON_VERSION, info.version),
        ("machine", REQUIRED_PYTHON_MACHINE, normalized_machine),
        ("bits", REQUIRED_PYTHON_BITS, info.bits),
    )
    for field, expected, actual in checks:
        if actual != expected:
            raise ValueError(f"Portable Python {field}: expected {expected}, actual {getattr(info, field)}")
    return PythonRuntimeInfo(info.version, REQUIRED_PYTHON_MACHINE, info.bits)


def build_base_install_command(
    uv_executable: str,
    python_exe: Path,
    requirements: Path,
    target: Path,
) -> list[str]:
    return [
        uv_executable,
        "pip",
        "install",
        "--python",
        str(python_exe),
        "--target",
        str(target),
        "--requirements",
        str(requirements),
        "--no-progress",
    ]


def _copy_python_runtime(source_home: Path, package_dir: Path) -> Path:
    target = package_dir / "runtime" / "python"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source_home,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "test", "tests"),
    )
    shutil.rmtree(target / "Scripts", ignore_errors=True)
    return target


def _install_base_dependencies(
    package_dir: Path,
    *,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    uv_executable: str | None = None,
    log_path: Path | None = None,
) -> None:
    python_exe = package_dir / "runtime" / "python" / "python.exe"
    requirements = package_dir / "packaging" / "requirements-portable-base.txt"
    target = package_dir / "runtime" / "site-packages"
    target.mkdir(parents=True, exist_ok=True)
    uv_executable = uv_executable or shutil.which("uv")
    if not uv_executable:
        raise RuntimeError("uv executable was not found; install uv or pass uv_executable.")
    command = build_base_install_command(uv_executable, python_exe, requirements, target)
    result = run(command, capture_output=True, text=True, check=False)
    log_path = log_path or package_dir / "runtime" / "logs" / "bootstrap.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_text = f"$ {' '.join(command)}\n\nSTDOUT\n{result.stdout or ''}\n\nSTDERR\n{result.stderr or ''}\n"
    log_text = re.sub(
        r"([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@",
        r"\1<redacted>@",
        log_text,
    )
    sensitive_paths = (
        (str(package_dir), "%PACKAGE_ROOT%"),
        (str(python_exe.parent), "%PYTHON_HOME%"),
        (str(uv_executable), "%UV_EXECUTABLE%"),
        (str(Path.home()), "%USER_HOME%"),
        (tempfile.gettempdir(), "%TEMP%"),
    )
    replacements: list[tuple[str, str]] = []
    for value, replacement in sensitive_paths:
        if value:
            replacements.extend(
                ((value, replacement), (value.replace("\\", "/"), replacement))
            )
    for value, replacement in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
        log_text = log_text.replace(value, replacement)
    log_path.write_text(log_text, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Base dependency installation failed. See {log_path}")
    shutil.rmtree(target / "bin", ignore_errors=True)


def _create_env_files(package_dir: Path) -> None:
    for relative in (Path("rag-anything-api"), Path("ai-tutor-system")):
        example = package_dir / relative / ".env.example"
        target = package_dir / relative / ".env"
        if example.exists():
            shutil.copy2(example, target)


def _resolve_executable(candidate: str | None, name: str) -> Path | None:
    if candidate:
        path = Path(candidate)
        if path.is_file():
            return path
        executable = path / name
        if executable.exists():
            return executable
    found = shutil.which(name)
    return Path(found) if found else None


def _copy_ffmpeg(package_dir: Path, candidate: str | None) -> bool:
    executable = _resolve_executable(candidate or os.getenv("FFMPEG_BIN"), "ffmpeg.exe")
    if not executable:
        return False
    target = package_dir / "runtime" / "tools" / "ffmpeg" / "bin"
    shutil.copytree(executable.parent, target, dirs_exist_ok=True)
    return True


def _copy_libreoffice(package_dir: Path, candidate: str | None) -> bool:
    executable = _resolve_executable(candidate or os.getenv("LIBREOFFICE_PATH"), "soffice.exe")
    if not executable:
        return False
    source_root = executable.parent.parent if executable.parent.name.lower() == "program" else executable.parent
    target = package_dir / "runtime" / "tools" / "LibreOffice"
    shutil.copytree(source_root, target, dirs_exist_ok=True)
    return True


def write_manifest(
    manifest_path: Path,
    *,
    python_info: PythonRuntimeInfo,
    ffmpeg_available: bool,
    libreoffice_available: bool,
) -> None:
    payload = {
        "package": PACKAGE_NAME,
        "python": {
            "version": python_info.version,
            "machine": python_info.machine,
            "bits": python_info.bits,
            "path": "runtime/python/python.exe",
        },
        "base_site_packages": {
            "path": "runtime/site-packages",
        },
        "mineru": {
            "bundled": False,
            "requirements": "packaging/mineru-requirements.txt",
            "install_target": "runtime/optional-site-packages",
            "model_cache": "runtime/models/mineru",
        },
        "ffmpeg": {"available": ffmpeg_available},
        "libreoffice": {"available": libreoffice_available},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_package(
    root: Path,
    output_root: Path,
    python_home: Path,
    *,
    ffmpeg_bin: str | None = None,
    libreoffice_path: str | None = None,
    archive: bool = True,
) -> Path:
    root = root.resolve()
    python_home = python_home.resolve()
    python_info = validate_python_runtime(python_home)
    out_dir = (root / output_root).resolve() if not output_root.is_absolute() else output_root.resolve()
    package_dir = out_dir / PACKAGE_NAME
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    for item in INCLUDE_ITEMS:
        source = root / item
        if source.exists():
            copy_filtered(source, package_dir / item, root)
    normalize_batch_line_endings(package_dir)

    _copy_python_runtime(python_home, package_dir)
    for path in (
        package_dir / "runtime" / "site-packages",
        package_dir / "runtime" / "optional-site-packages",
        package_dir / "runtime" / "models" / "mineru",
        package_dir / "runtime" / "logs",
    ):
        path.mkdir(parents=True, exist_ok=True)

    _install_base_dependencies(package_dir)
    _create_env_files(package_dir)
    ffmpeg_available = _copy_ffmpeg(package_dir, ffmpeg_bin)
    libreoffice_available = _copy_libreoffice(package_dir, libreoffice_path)
    write_manifest(
        package_dir / "runtime" / "portable-manifest.json",
        python_info=python_info,
        ffmpeg_available=ffmpeg_available,
        libreoffice_available=libreoffice_available,
    )

    if not archive:
        return package_dir
    zip_path = out_dir / f"{PACKAGE_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=out_dir, base_dir=PACKAGE_NAME)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Test-System portable package.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-root", default="dist-portable")
    parser.add_argument("--python-home", required=True)
    parser.add_argument("--ffmpeg-bin", default=None)
    parser.add_argument("--libreoffice-path", default=None)
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args()
    result = build_package(
        Path(args.root),
        Path(args.output_root),
        Path(args.python_home),
        ffmpeg_bin=args.ffmpeg_bin,
        libreoffice_path=args.libreoffice_path,
        archive=not args.no_archive,
    )
    print(f"Portable package created: {result}")


if __name__ == "__main__":
    main()
