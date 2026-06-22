from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    module_path = ROOT / "packaging" / "installer_builder.py"
    spec = importlib.util.spec_from_file_location("installer_builder", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str = "content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _source_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "source"
    _write(root / "version.json", '{"version":"2.3.4"}')
    _write(root / "LICENSE", "license")
    _write(root / "README.md", "readme")
    _write(root / "使用说明.md", "guide")
    _write(root / "docs" / "superpowers" / "secret.md", "excluded")
    _write(root / "ai-tutor-system" / "app.py")
    _write(root / "ai-tutor-system" / ".env.example", "API_KEY=\nSAFE=true\n")
    _write(root / "ai-tutor-system" / "tests" / "test_app.py")
    _write(root / "ai-tutor-system" / "tutor_data" / "private.json")
    _write(root / "rag-anything-api" / "api.py")
    _write(root / "rag-anything-api" / ".env.example", "SECRET=\n")
    _write(root / "rag-anything-api" / "storage" / "output" / "result.txt")
    _write(root / "assets" / "logo.txt")
    _write(root / "models" / "cache" / "model.bin")
    _write(root / "dist" / "old.bin")
    _write(root / "packaging" / "portable_builder.py", (ROOT / "packaging" / "portable_builder.py").read_text(encoding="utf-8"))
    _write(root / "packaging" / "product_version.py", (ROOT / "packaging" / "product_version.py").read_text(encoding="utf-8"))
    _write(root / "packaging" / "internal_release_script.py", "raise SystemExit")
    requirements = "# CPython 3.13.10 x64 lock target\nfastapi==0.136.1\n"
    _write(root / "packaging" / "requirements-portable-base.txt", requirements)

    python_home = tmp_path / "python"
    _write(python_home / "python.exe", "exe")
    _write(python_home / "python313.dll", "dll")

    desktop_publish = tmp_path / "desktop"
    _write(desktop_publish / "TestSystem.exe", "host")
    _write(desktop_publish / "host.dll", "host dependency")
    _write(desktop_publish / "runtimes" / "win-x64" / "native.dll", "native")
    return root, python_home, desktop_publish


def _fake_run(command, **kwargs):
    if command[1:2] == ["-c"]:
        payload = {"version": "3.13.10", "machine": "AMD64", "bits": "64bit"}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")
    target = Path(command[command.index("--target") + 1])
    _write(target / "fastapi" / "__init__.py", "installed")
    return subprocess.CompletedProcess(command, 0, stdout="installed", stderr="")


def _build(tmp_path: Path, **overrides) -> Path:
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    arguments = {
        "root": root,
        "output_root": tmp_path / "output",
        "python_home": python_home,
        "desktop_publish": desktop_publish,
        "uv_executable": "fake-uv.exe",
    }
    arguments.update(overrides)
    return builder.build_install_image(**arguments)


def test_build_install_image_stages_runtime_files_and_excludes_build_data(tmp_path: Path):
    stage = _build(tmp_path)

    assert stage == tmp_path / "output" / "Test-System"
    for relative in (
        "TestSystem.exe",
        "host.dll",
        "runtimes/win-x64/native.dll",
        "ai-tutor-system/app.py",
        "rag-anything-api/api.py",
        "assets/logo.txt",
        "runtime/python/python.exe",
        "runtime/site-packages/fastapi/__init__.py",
        "ai-tutor-system/.env",
        "rag-anything-api/.env",
    ):
        assert (stage / relative).exists(), relative

    for relative in (
        "docs",
        "ai-tutor-system/tests",
        "ai-tutor-system/tutor_data",
        "rag-anything-api/storage/output",
        "models",
        "dist",
        "runtime/optional-site-packages",
        "runtime/models",
        "packaging/internal_release_script.py",
    ):
        assert not (stage / relative).exists(), relative


def test_install_manifest_has_relative_paths_hash_version_and_runtime_contract(tmp_path: Path):
    stage = _build(tmp_path)
    manifest_text = (stage / "runtime" / "install-manifest.json").read_text(encoding="utf-8")
    data = json.loads(manifest_text)
    requirements = stage / "packaging" / "requirements-portable-base.txt"

    assert data["product"]["version"] == "2.3.4"
    assert data["python"] == {
        "version": "3.13.10",
        "machine": "AMD64",
        "bits": "64bit",
        "path": "runtime/python/python.exe",
    }
    assert data["base_site_packages"]["path"] == "runtime/site-packages"
    assert data["base_site_packages"]["requirements_path"] == "packaging/requirements-portable-base.txt"
    assert data["base_site_packages"]["requirements_sha256"] == hashlib.sha256(requirements.read_bytes()).hexdigest()
    assert data["desktop"] == {
        "host_path": "TestSystem.exe",
        "webview2_sdk_version": "1.0.4022.49",
    }
    assert data["mineru"] == {
        "bundled": False,
        "data_dir_intent": "per-user-local-app-data",
    }
    assert data["ffmpeg"] == {"available": False, "path": None}
    assert data["libreoffice"] == {"available": False, "path": None}
    assert str(tmp_path) not in manifest_text


def test_install_image_copies_optional_tools_and_records_relative_paths(tmp_path: Path):
    ffmpeg = tmp_path / "ffmpeg" / "bin"
    libreoffice = tmp_path / "LibreOffice" / "program"
    _write(ffmpeg / "ffmpeg.exe", "ffmpeg")
    _write(libreoffice / "soffice.exe", "soffice")

    stage = _build(tmp_path, ffmpeg_bin=str(ffmpeg), libreoffice_path=str(libreoffice))
    data = json.loads((stage / "runtime" / "install-manifest.json").read_text(encoding="utf-8"))

    assert data["ffmpeg"] == {"available": True, "path": "runtime/tools/ffmpeg/bin/ffmpeg.exe"}
    assert data["libreoffice"] == {
        "available": True,
        "path": "runtime/tools/LibreOffice/program/soffice.exe",
    }


def test_install_image_cleanly_rebuilds_target(tmp_path: Path):
    stage = _build(tmp_path)
    _write(stage / "stale.txt", "stale")

    rebuilt = _build(tmp_path)

    assert rebuilt == stage
    assert not (rebuilt / "stale.txt").exists()


@pytest.mark.parametrize("host_state", ["missing-directory", "missing-executable"])
def test_install_image_rejects_missing_desktop_host_and_cleans_target(tmp_path: Path, host_state: str):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    _write(target / "stale-success.txt")
    if host_state == "missing-directory":
        desktop_publish = tmp_path / "absent"
    else:
        (desktop_publish / "TestSystem.exe").unlink()

    with pytest.raises(FileNotFoundError, match="TestSystem.exe|desktop publish"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert not target.exists()


def test_install_image_rejects_invalid_python_and_cleans_target(tmp_path: Path):
    builder = _load_builder()
    root, python_home, desktop_publish = _source_tree(tmp_path)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    _write(target / "stale-success.txt")

    def invalid_python(command, **kwargs):
        payload = {"version": "3.13.10", "machine": "ARM64", "bits": "64bit"}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    builder._run = invalid_python

    with pytest.raises(ValueError, match="expected AMD64.*actual ARM64"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert not target.exists()
