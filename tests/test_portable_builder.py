from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    module_path = ROOT / "packaging" / "portable_builder.py"
    spec = importlib.util.spec_from_file_location("portable_builder", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_uses_bundled_python_without_copied_venv():
    text = (ROOT / "start_services.bat").read_text(encoding="utf-8")

    assert r"runtime\python\python.exe" in text
    assert 'set "VENV=' not in text
    assert "activate.bat" not in text
    assert r".venv\Scripts" not in text
    assert '"%PYTHON%" start.py' in text
    assert '"%PYTHON%" tutor_backend.py' in text


def test_launcher_checks_runtime_and_offers_mineru_install():
    text = (ROOT / "start_services.bat").read_text(encoding="utf-8")

    assert 'set "RUNTIME_MANAGER=%ROOT%packaging\\portable_runtime.py"' in text
    assert '"%RUNTIME_MANAGER%" check --root "%ROOT%."' in text
    assert '"%RUNTIME_MANAGER%" install-mineru --root "%ROOT%."' in text
    assert '--root "%ROOT%"' not in text
    assert '--cmd-output "%RUNTIME_VARS%"' in text
    assert 'call "%RUNTIME_VARS%"' in text
    assert "ConvertFrom-Json" not in text
    assert "powershell" not in text.lower()
    assert '"%RUNTIME_MANAGER%" check-url' in text
    assert "choice /C YN" in text
    assert "MinerU" in text


def test_manual_mineru_installer_uses_bundled_python():
    text = (ROOT / "install_mineru.bat").read_text(encoding="utf-8")

    assert r"runtime\python\python.exe" in text
    assert 'set "RUNTIME_MANAGER=%ROOT%packaging\\portable_runtime.py"' in text
    assert '"%RUNTIME_MANAGER%" install-mineru --root "%ROOT%."' in text
    assert '--root "%ROOT%"' not in text


def test_windows_launchers_use_crlf_line_endings():
    for name in ("start_services.bat", "install_mineru.bat"):
        content = (ROOT / name).read_bytes()

        assert b"\n" in content
        assert b"\n" not in content.replace(b"\r\n", b"")


def test_builder_normalizes_packaged_batch_files(tmp_path: Path):
    builder = _load_builder()
    package_dir = tmp_path / "Test-System-Portable"
    nested = package_dir / "tools"
    nested.mkdir(parents=True)
    (package_dir / "start_services.bat").write_bytes(b"@echo off\necho root\n")
    (nested / "helper.bat").write_bytes(b"@echo off\r\necho nested\r\n")

    builder.normalize_batch_line_endings(package_dir)

    for path in package_dir.rglob("*.bat"):
        content = path.read_bytes()
        assert b"\n" not in content.replace(b"\r\n", b"")


def test_builder_excludes_venv_user_data_and_model_caches():
    builder = _load_builder()

    excluded = [
        Path(".venv/Lib/site-packages/fastapi/__init__.py"),
        Path("rag-anything-api/.env"),
        Path("rag-anything-api/storage/databases.json"),
        Path("ai-tutor-system/tutor_data/sessions/a.json"),
        Path("runtime/models/mineru/model.bin"),
        Path("__pycache__/module.pyc"),
    ]
    for path in excluded:
        assert builder.should_exclude(path)

    assert not builder.should_exclude(Path("rag-anything-api/.env.example"))
    assert not builder.should_exclude(Path("packaging/portable_runtime.py"))


def test_validate_python_runtime_requires_exact_31310(tmp_path: Path):
    builder = _load_builder()
    python_home = tmp_path / "python"
    python_home.mkdir()
    (python_home / "python.exe").write_bytes(b"exe")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="3.13.12\n", stderr="")

    try:
        builder.validate_python_runtime(python_home, run=fake_run)
    except ValueError as exc:
        assert "3.13.10" in str(exc)
        assert "3.13.12" in str(exc)
    else:
        raise AssertionError("Expected exact-version validation failure")


def test_base_install_command_targets_package_site_packages(tmp_path: Path):
    builder = _load_builder()
    python_exe = tmp_path / "runtime" / "python" / "python.exe"
    requirements = tmp_path / "packaging" / "requirements-portable-base.txt"
    target = tmp_path / "runtime" / "site-packages"

    command = builder.build_base_install_command("uv.exe", python_exe, requirements, target)

    assert command[:3] == ["uv.exe", "pip", "install"]
    assert command[command.index("--python") + 1] == str(python_exe)
    assert command[command.index("--target") + 1] == str(target)
    assert command[command.index("--requirements") + 1] == str(requirements)


def test_portable_base_requirements_include_lightrag_openai_client():
    requirements = (ROOT / "packaging" / "requirements-portable-base.txt").read_text(encoding="utf-8")

    assert "openai==2.36.0" in requirements.splitlines()


def test_manifest_uses_relative_paths(tmp_path: Path):
    builder = _load_builder()
    package_dir = tmp_path / "Test-System-Portable"
    manifest_path = package_dir / "runtime" / "portable-manifest.json"

    builder.write_manifest(manifest_path, python_version="3.13.10", ffmpeg_available=True, libreoffice_available=False)

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["python"]["path"] == "runtime/python/python.exe"
    assert data["base_site_packages"]["path"] == "runtime/site-packages"
    assert data["mineru"]["bundled"] is False
    assert str(tmp_path) not in manifest_path.read_text(encoding="utf-8")


def test_powershell_builder_locates_exact_python_and_passes_home():
    text = (ROOT / "packaging" / "package_windows.ps1").read_text(encoding="utf-8")

    assert "3.13.10" in text
    assert "uv python install" in text
    assert '"--python-home"' in text
    assert ".venv" not in text


def test_bootstrap_log_does_not_leak_build_machine_package_path(tmp_path: Path):
    builder = _load_builder()
    package_dir = tmp_path / "Test-System-Portable"
    (package_dir / "runtime" / "python").mkdir(parents=True)
    (package_dir / "runtime" / "python" / "python.exe").write_bytes(b"exe")
    (package_dir / "packaging").mkdir()
    (package_dir / "packaging" / "requirements-portable-base.txt").write_text(
        "fastapi==0\n",
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):
        target = Path(command[command.index("--target") + 1])
        (target / "bin").mkdir(parents=True, exist_ok=True)
        (target / "bin" / "uvicorn.exe").write_bytes(b"absolute launcher")
        return subprocess.CompletedProcess(command, 0, stdout=f"installed into {package_dir}", stderr="")

    builder._install_base_dependencies(package_dir, run=fake_run)

    log_text = (package_dir / "runtime" / "logs" / "bootstrap.log").read_text(encoding="utf-8")
    assert str(package_dir) not in log_text
    assert "%PACKAGE_ROOT%" in log_text
    assert not (package_dir / "runtime" / "site-packages" / "bin").exists()
