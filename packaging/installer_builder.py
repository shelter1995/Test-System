from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType


PACKAGE_NAME = "Test-System"

SOURCE_DIRECTORIES = ("ai-tutor-system", "rag-anything-api", "assets")
USER_DOCUMENTS = (
    "LICENSE",
    "LICENSE.md",
    "README.md",
    "SETUP.md",
    "CHANGELOG.md",
    "使用说明.md",
    "部署说明.md",
    "rag_database_guide.md",
)
PACKAGING_FILES = (
    "installer_builder.py",
    "portable_builder.py",
    "portable_runtime.py",
    "product_version.py",
    "requirements-portable-base.txt",
    "mineru-requirements.txt",
)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "tests",
    "docs",
    "superpowers",
    "tutor_data",
    "generation_output",
    "models",
    "cache",
    "dist",
    "build",
    "__pycache__",
}

_run = subprocess.run


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _is_excluded(relative_path: Path) -> bool:
    parts = tuple(part.lower() for part in relative_path.parts)
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    if parts and parts[-1] == ".env":
        return True
    if len(parts) >= 2 and parts[0] == "rag-anything-api" and parts[1] in {"storage", "output"}:
        return True
    return False


def _copy_source_item(source: Path, target: Path, root: Path) -> None:
    if _is_excluded(source.relative_to(root)):
        return
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy_source_item(child, target / child.name, root)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_application_sources(root: Path, stage: Path) -> None:
    for name in SOURCE_DIRECTORIES:
        source = root / name
        if source.exists():
            _copy_source_item(source, stage / name, root)
    for name in USER_DOCUMENTS:
        source = root / name
        if source.is_file():
            shutil.copy2(source, stage / name)
    version_file = root / "version.json"
    if version_file.is_file():
        shutil.copy2(version_file, stage / "version.json")

    packaging_source = root / "packaging"
    packaging_target = stage / "packaging"
    if packaging_source.is_dir():
        for name in PACKAGING_FILES:
            source = packaging_source / name
            if source.is_file():
                packaging_target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, packaging_target / name)


def _requirements_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(
    stage: Path,
    *,
    product_version: str,
    python_info,
    webview_sdk_version: str,
    ffmpeg_available: bool,
    libreoffice_available: bool,
) -> None:
    payload = {
        "product": {"version": product_version},
        "python": {
            "version": python_info.version,
            "machine": python_info.machine,
            "bits": python_info.bits,
            "path": "runtime/python/python.exe",
        },
        "base_site_packages": {
            "path": "runtime/site-packages",
            "requirements_path": "packaging/requirements-portable-base.txt",
            "requirements_sha256": _requirements_sha256(
                stage / "packaging" / "requirements-portable-base.txt"
            ),
        },
        "desktop": {
            "host_path": "TestSystem.exe",
            "webview2_sdk_version": webview_sdk_version,
        },
        "mineru": {
            "bundled": False,
            "data_dir_intent": "per-user-local-app-data",
        },
        "ffmpeg": {
            "available": ffmpeg_available,
            "path": "runtime/tools/ffmpeg/bin/ffmpeg.exe" if ffmpeg_available else None,
        },
        "libreoffice": {
            "available": libreoffice_available,
            "path": (
                "runtime/tools/LibreOffice/program/soffice.exe"
                if libreoffice_available
                else None
            ),
        },
    }
    manifest_path = stage / "runtime" / "install-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_install_image(
    root: Path,
    output_root: Path,
    python_home: Path,
    desktop_publish: Path,
    *,
    version_file: Path,
    ffmpeg_bin: str | None,
    libreoffice_path: str | None,
    uv_executable: str | None,
    webview_sdk_version: str,
) -> Path:
    root = root.resolve()
    output_root = (root / output_root).resolve() if not output_root.is_absolute() else output_root.resolve()
    python_home = python_home.resolve()
    desktop_publish = desktop_publish.resolve()
    version_file = version_file.resolve()
    target = output_root / PACKAGE_NAME
    temporary = output_root / f".{PACKAGE_NAME}.building"

    output_root.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    shutil.rmtree(temporary, ignore_errors=True)

    try:
        if not desktop_publish.is_dir():
            raise FileNotFoundError(f"desktop publish directory not found: {desktop_publish}")
        host = desktop_publish / "TestSystem.exe"
        if not host.is_file():
            raise FileNotFoundError(f"Desktop publish is missing TestSystem.exe: {host}")

        portable = _load_module(root / "packaging" / "portable_builder.py", "_installer_portable_builder")
        product_versions = _load_module(root / "packaging" / "product_version.py", "_installer_product_version")
        python_info = portable.validate_python_runtime(python_home, run=_run)
        product_version = product_versions.read_product_version(version_file).text

        temporary.mkdir(parents=True)
        _copy_application_sources(root, temporary)
        if version_file != root / "version.json":
            shutil.copy2(version_file, temporary / "version.json")
        shutil.copytree(desktop_publish, temporary, dirs_exist_ok=True)

        portable._copy_python_runtime(python_home, temporary)
        portable._install_base_dependencies(
            temporary,
            run=_run,
            uv_executable=uv_executable,
        )
        portable._create_env_files(temporary)
        ffmpeg_available = bool(ffmpeg_bin) and portable._copy_ffmpeg(temporary, ffmpeg_bin)
        libreoffice_available = bool(libreoffice_path) and portable._copy_libreoffice(
            temporary, libreoffice_path
        )
        _write_manifest(
            temporary,
            product_version=product_version,
            python_info=python_info,
            webview_sdk_version=webview_sdk_version,
            ffmpeg_available=ffmpeg_available,
            libreoffice_available=libreoffice_available,
        )

        temporary.replace(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)
        raise


def build_install_image(
    root: Path,
    output_root: Path,
    python_home: Path,
    desktop_publish: Path,
    *,
    ffmpeg_bin: str | None = None,
    libreoffice_path: str | None = None,
    uv_executable: str | None = None,
    webview_sdk_version: str = "1.0.4022.49",
) -> Path:
    return _build_install_image(
        root,
        output_root,
        python_home,
        desktop_publish,
        version_file=root / "version.json",
        ffmpeg_bin=ffmpeg_bin,
        libreoffice_path=libreoffice_path,
        uv_executable=uv_executable,
        webview_sdk_version=webview_sdk_version,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Test-System Windows install image.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--python-home", type=Path, required=True)
    parser.add_argument("--desktop-publish", type=Path, required=True)
    parser.add_argument("--version-file", type=Path)
    parser.add_argument("--ffmpeg-bin")
    parser.add_argument("--libreoffice-path")
    parser.add_argument("--uv-executable")
    parser.add_argument("--webview-sdk-version", default="1.0.4022.49")
    args = parser.parse_args()

    result = _build_install_image(
        args.root,
        args.output_root,
        args.python_home,
        args.desktop_publish,
        version_file=args.version_file or args.root / "version.json",
        ffmpeg_bin=args.ffmpeg_bin,
        libreoffice_path=args.libreoffice_path,
        uv_executable=args.uv_executable,
        webview_sdk_version=args.webview_sdk_version,
    )
    print(f"Install image created: {result}")


if __name__ == "__main__":
    main()
