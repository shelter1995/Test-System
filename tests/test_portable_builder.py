from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    module_path = ROOT / "packaging" / "portable_builder.py"
    spec = importlib.util.spec_from_file_location("portable_builder", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_launcher_prefers_bundled_python_and_supports_source_checkout_venv():
    text = (ROOT / "start_services.bat").read_text(encoding="utf-8")

    assert r'set "PORTABLE_PYTHON=%ROOT%runtime\python\python.exe"' in text
    assert r'set "DEV_PYTHON=%ROOT%.venv\Scripts\python.exe"' in text
    assert 'set "PYTHON=%PORTABLE_PYTHON%"' in text
    assert 'if not exist "%PYTHON%" if exist "%DEV_PYTHON%"' in text
    assert 'set "RUNTIME_MODE=development"' in text
    assert 'if /I "%RUNTIME_MODE%"=="development" goto runtime_ready' in text
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


def _python_home(tmp_path: Path) -> Path:
    python_home = tmp_path / "python"
    python_home.mkdir()
    (python_home / "python.exe").write_bytes(b"exe")
    return python_home


def _runtime_result(command, *, version="3.13.10", machine="AMD64", bits="64bit"):
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps({"version": version, "machine": machine, "bits": bits}),
        stderr="",
    )


def test_validate_python_runtime_returns_structured_amd64_info(tmp_path: Path):
    builder = _load_builder()
    python_home = _python_home(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return _runtime_result(command, machine="amd64")

    info = builder.validate_python_runtime(python_home, run=fake_run)

    assert info == builder.PythonRuntimeInfo(version="3.13.10", machine="AMD64", bits="64bit")
    assert len(calls) == 1
    assert "json.dumps" in calls[0][2]


@pytest.mark.parametrize(
    ("field", "actual", "expected"),
    [
        ("version", "3.13.12", "3.13.10"),
        ("machine", "x86_64", "AMD64"),
        ("bits", "32bit", "64bit"),
    ],
)
def test_validate_python_runtime_rejects_non_target_runtime(
    tmp_path: Path, field: str, actual: str, expected: str
):
    builder = _load_builder()
    python_home = _python_home(tmp_path)

    values = {"version": "3.13.10", "machine": "AMD64", "bits": "64bit"}
    values[field] = actual

    def fake_run(command, **kwargs):
        return _runtime_result(command, **values)

    with pytest.raises(ValueError) as exc_info:
        builder.validate_python_runtime(python_home, run=fake_run)

    message = str(exc_info.value)
    assert f"expected {expected}" in message
    assert f"actual {actual}" in message


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


def test_portable_base_requirements_are_pinned_for_cpython_31310_x64_without_mineru():
    lines = (ROOT / "packaging" / "requirements-portable-base.txt").read_text(
        encoding="utf-8"
    ).splitlines()

    assert lines[0] == "# CPython 3.13.10 x64 lock target; all runtime dependencies must remain pinned."
    dependencies = [line for line in lines if line and not line.startswith("#")]
    assert dependencies
    assert all("==" in dependency for dependency in dependencies)
    assert all("mineru" not in dependency.lower() for dependency in dependencies)


def test_manifest_uses_relative_paths(tmp_path: Path):
    builder = _load_builder()
    package_dir = tmp_path / "Test-System-Portable"
    manifest_path = package_dir / "runtime" / "portable-manifest.json"

    builder.write_manifest(
        manifest_path,
        python_info=builder.PythonRuntimeInfo("3.13.10", "AMD64", "64bit"),
        ffmpeg_available=True,
        libreoffice_available=False,
    )

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["python"]["path"] == "runtime/python/python.exe"
    assert data["python"]["machine"] == "AMD64"
    assert data["python"]["bits"] == "64bit"
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

    builder._install_base_dependencies(package_dir, run=fake_run, uv_executable="fake-uv.exe")

    log_text = (package_dir / "runtime" / "logs" / "bootstrap.log").read_text(encoding="utf-8")
    assert str(package_dir) not in log_text
    assert "%PACKAGE_ROOT%" in log_text
    assert not (package_dir / "runtime" / "site-packages" / "bin").exists()


def test_install_base_dependencies_reports_missing_uv(tmp_path: Path, monkeypatch):
    builder = _load_builder()
    monkeypatch.setattr(builder.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="uv executable was not found"):
        builder._install_base_dependencies(tmp_path)
