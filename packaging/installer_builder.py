from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import uuid
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
ROOT_SCRIPTS = (
    "start_services.bat",
    "install_mineru.bat",
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
RESERVED_DESKTOP_NAMES = {
    "version.json",
    "runtime",
    "packaging",
    "assets",
    "ai-tutor-system",
    "rag-anything-api",
}

_run = subprocess.run


def _replace_path(source: Path, destination: Path) -> None:
    source.replace(destination)


def _acquire_lock(lock_path: Path, owner: str) -> None:
    try:
        with lock_path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(owner)
    except FileExistsError as exc:
        raise RuntimeError("another installer build is already running in this output root") from exc


def _release_lock(lock_path: Path, owner: str) -> None:
    try:
        if lock_path.read_text(encoding="utf-8") == owner:
            lock_path.unlink()
    except FileNotFoundError:
        pass


def _resolve_uv_executable(candidate: str | None) -> str:
    discovered = candidate or shutil.which("uv")
    if not discovered:
        raise FileNotFoundError("uv executable was not found on PATH")
    resolved = Path(discovered)
    if not resolved.is_file():
        raise FileNotFoundError(f"uv executable is not a file: {resolved}")
    return str(resolved.resolve())


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def collect_tracked_files(root: Path) -> set[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"git ls-files failed for source root: {detail}")
    return {
        Path(item.decode(errors="surrogateescape"))
        for item in (result.stdout or b"").split(b"\0")
        if item
    }


def is_reparse_point(path) -> bool:
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve(strict=False)
    second = second.resolve(strict=False)
    return _is_within(first, second) or _is_within(second, first)


def _validate_safe_path(path: Path, approved_root: Path) -> None:
    approved_root = approved_root.absolute()
    path = path.absolute()
    try:
        relative = path.relative_to(approved_root)
    except ValueError as exc:
        raise ValueError(f"Path escapes approved source root: {path}") from exc
    current = approved_root
    for part in (Path("."), *relative.parts):
        current = current if part == Path(".") else current / part
        if is_reparse_point(current):
            raise ValueError(f"symlink or reparse point is not allowed: {current}")
    resolved_root = approved_root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if not _is_within(resolved, resolved_root):
        raise ValueError(f"Resolved path escapes approved source root: {path}")


def _is_excluded(relative_path: Path) -> bool:
    parts = tuple(part.lower() for part in relative_path.parts)
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    if parts and parts[-1] == ".env":
        return True
    if len(parts) >= 2 and parts[0] == "rag-anything-api" and parts[1] in {"storage", "output"}:
        return True
    return False


def _allowed_source_destination(relative: Path) -> Path | None:
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return None
    if _is_excluded(relative):
        return None
    if relative.parts[0] in SOURCE_DIRECTORIES:
        return relative
    if len(relative.parts) == 1 and relative.name in (*USER_DOCUMENTS, *ROOT_SCRIPTS, "version.json"):
        return relative
    if (
        len(relative.parts) == 2
        and relative.parts[0] == "packaging"
        and relative.parts[1] in PACKAGING_FILES
    ):
        return relative
    return None


def _plan_application_sources(root: Path, tracked_files: set[Path]) -> list[tuple[Path, Path]]:
    planned: list[tuple[Path, Path]] = []
    for relative in sorted(tracked_files, key=lambda item: item.as_posix()):
        destination = _allowed_source_destination(relative)
        if destination is None:
            continue
        source = root / relative
        if not source.exists():
            raise FileNotFoundError(f"Tracked source file is missing: {source}")
        _validate_safe_path(source, root)
        if not source.is_file():
            raise ValueError(f"Tracked source must be a regular file: {source}")
        planned.append((source, destination))
    return planned


def _copy_application_sources(stage: Path, planned: list[tuple[Path, Path]]) -> None:
    for source, relative in planned:
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _plan_desktop_publish(desktop_publish: Path, source_destinations: set[Path]) -> list[tuple[Path, Path]]:
    if not desktop_publish.is_dir():
        raise FileNotFoundError(f"desktop publish directory not found: {desktop_publish}")
    _validate_safe_path(desktop_publish, desktop_publish)
    planned: list[tuple[Path, Path]] = []
    pending = [desktop_publish]
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            _validate_safe_path(child, desktop_publish)
            relative = child.relative_to(desktop_publish)
            if relative.parts[0].lower() in RESERVED_DESKTOP_NAMES:
                raise ValueError(f"Desktop publish uses reserved top-level name: {relative.parts[0]}")
            if child.is_dir():
                pending.append(child)
                continue
            if not child.is_file():
                raise ValueError(f"Desktop publish item must be a regular file: {child}")
            if relative in source_destinations:
                raise ValueError(f"Desktop publish destination collision: {relative}")
            planned.append((child, relative))
    if not any(relative == Path("TestSystem.exe") for _, relative in planned):
        raise FileNotFoundError(
            f"Desktop publish is missing TestSystem.exe: {desktop_publish / 'TestSystem.exe'}"
        )
    return planned


def _copy_desktop_publish(stage: Path, planned: list[tuple[Path, Path]]) -> None:
    for source, relative in planned:
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _validate_topology(
    root: Path,
    target: Path,
    stage: Path,
    desktop_publish: Path,
    python_home: Path,
) -> None:
    for name in (*SOURCE_DIRECTORIES, "packaging"):
        source = root / name
        if source.exists() and (_paths_overlap(target, source) or _paths_overlap(stage, source)):
            raise ValueError(f"Installer output paths overlap copied source: {source}")
    for label, source in (("desktop publish", desktop_publish), ("python home", python_home)):
        if _paths_overlap(source, target) or _paths_overlap(source, stage):
            raise ValueError(f"{label} must not overlap installer target or staging path")


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
    root = root.absolute()
    output_root = (root / output_root).absolute() if not output_root.is_absolute() else output_root.absolute()
    python_home = python_home.absolute()
    desktop_publish = desktop_publish.absolute()
    version_file = (root / version_file).absolute() if not version_file.is_absolute() else version_file.absolute()
    target = output_root / PACKAGE_NAME
    owner = uuid.uuid4().hex
    temporary = output_root / f".{PACKAGE_NAME}.building-{owner}"
    backup = output_root / f".{PACKAGE_NAME}.backup-{owner}"
    lock_path = output_root / f".{PACKAGE_NAME}.lock"

    _validate_topology(root, target, temporary, desktop_publish, python_home)
    tracked_files = collect_tracked_files(root)
    planned_sources = _plan_application_sources(root, tracked_files)
    source_destinations = {destination for _, destination in planned_sources}
    try:
        version_relative = version_file.relative_to(root)
    except ValueError as exc:
        raise ValueError("version file must be a tracked file inside the source root") from exc
    if version_relative not in tracked_files:
        raise ValueError("version file must be tracked by git")
    _validate_safe_path(version_file, root)
    planned_desktop = _plan_desktop_publish(desktop_publish, source_destinations)
    resolved_uv = _resolve_uv_executable(uv_executable)

    output_root.mkdir(parents=True, exist_ok=True)
    _acquire_lock(lock_path, owner)
    stage_owned = False

    try:
        portable = _load_module(root / "packaging" / "portable_builder.py", "_installer_portable_builder")
        product_versions = _load_module(root / "packaging" / "product_version.py", "_installer_product_version")
        python_info = portable.validate_python_runtime(python_home, run=_run)
        product_version = product_versions.read_product_version(version_file).text

        temporary.mkdir(parents=True)
        stage_owned = True
        _copy_application_sources(temporary, planned_sources)
        if version_file != root / "version.json":
            shutil.copy2(version_file, temporary / "version.json")
        _copy_desktop_publish(temporary, planned_desktop)

        portable._copy_python_runtime(python_home, temporary)
        portable._install_base_dependencies(
            temporary,
            run=_run,
            uv_executable=resolved_uv,
            log_path=output_root / "build-logs" / "bootstrap.log",
        )
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

        had_target = target.exists()
        if had_target:
            _replace_path(target, backup)
        try:
            _replace_path(temporary, target)
        except BaseException:
            if had_target and backup.exists() and not target.exists():
                _replace_path(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if stage_owned:
            shutil.rmtree(temporary, ignore_errors=True)
        _release_lock(lock_path, owner)


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
        version_file=Path("version.json"),
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

    try:
        result = _build_install_image(
            args.root,
            args.output_root,
            args.python_home,
            args.desktop_publish,
            version_file=args.version_file or Path("version.json"),
            ffmpeg_bin=args.ffmpeg_bin,
            libreoffice_path=args.libreoffice_path,
            uv_executable=args.uv_executable,
            webview_sdk_version=args.webview_sdk_version,
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Install image created: {result}")


if __name__ == "__main__":
    main()
