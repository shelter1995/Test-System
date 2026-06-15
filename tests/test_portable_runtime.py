from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path


def _load_runtime():
    module_path = Path(__file__).resolve().parents[1] / "packaging" / "portable_runtime.py"
    spec = importlib.util.spec_from_file_location("portable_runtime", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_package(tmp_path: Path) -> Path:
    root = tmp_path / "Test-System-Portable"
    (root / "runtime" / "python").mkdir(parents=True)
    (root / "runtime" / "site-packages").mkdir(parents=True)
    (root / "runtime" / "optional-site-packages").mkdir(parents=True)
    (root / "runtime" / "models" / "mineru").mkdir(parents=True)
    (root / "runtime" / "logs").mkdir(parents=True)
    (root / "packaging").mkdir(parents=True)
    return root


def test_configure_runtime_environment_uses_package_local_paths(tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    env = {"PATH": "C:\\Windows\\System32"}

    configured = runtime.configure_runtime_environment(root, env)

    assert configured["PYTHONPATH"].split(os.pathsep)[:2] == [
        str(root / "runtime" / "optional-site-packages"),
        str(root / "runtime" / "site-packages"),
    ]
    assert str(root / "rag-anything-api") in configured["PYTHONPATH"].split(os.pathsep)
    assert configured["HF_HOME"] == str(root / "runtime" / "models" / "mineru" / "huggingface")
    assert configured["MODELSCOPE_CACHE"] == str(root / "runtime" / "models" / "mineru" / "modelscope")
    assert configured["MINERU_TOOLS_CONFIG_JSON"] == str(
        root / "runtime" / "models" / "mineru" / "mineru.json"
    )
    assert configured["PATH"].split(os.pathsep)[0] == str(root / "runtime" / "python")


def test_probe_runtime_reports_base_and_optional_status(tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    imported = {
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
    }

    def fake_import(name: str):
        if name in imported:
            return object()
        raise ImportError(name)

    status = runtime.probe_runtime(root, importer=fake_import)

    assert status["python_ready"] is True
    assert status["base_dependencies_ready"] is True
    assert status["missing_base_modules"] == []
    assert status["uvicorn_importable"] is True
    assert status["raganything_importable"] is True
    assert status["openai_importable"] is True
    assert status["mineru_package_installed"] is False
    assert status["mineru_cli_runnable"] is False
    assert status["mineru_models_ready"] is False


def test_build_mineru_install_command_uses_current_python_and_pinned_file(tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    requirements = root / "packaging" / "mineru-requirements.txt"
    requirements.write_text('mineru[core]==3.3.1\n', encoding="utf-8")
    target = root / "runtime" / "optional-site-packages.installing"

    command = runtime.build_mineru_install_command(requirements, target)

    assert command[:4] == [runtime.sys.executable, "-m", "pip", "install"]
    assert command[-4:] == ["--target", str(target), "--requirement", str(requirements)]
    assert "-U" not in command
    assert "--upgrade" not in command


def test_install_mineru_uses_temporary_target_and_writes_log(tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    requirements = root / "packaging" / "mineru-requirements.txt"
    requirements.write_text('mineru[core]==3.3.1\n', encoding="utf-8")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), kwargs))
        target = Path(command[command.index("--target") + 1])
        (target / "mineru" / "cli").mkdir(parents=True, exist_ok=True)
        (target / "mineru" / "__init__.py").write_text("", encoding="utf-8")
        (target / "mineru" / "cli" / "__init__.py").write_text("", encoding="utf-8")
        (target / "mineru" / "cli" / "client.py").write_text("def main(): pass\n", encoding="utf-8")
        (target / "bin").mkdir()
        (target / "bin" / "mineru.exe").write_bytes(b"absolute launcher")
        return subprocess.CompletedProcess(command, 0, stdout="installed", stderr="")

    result = runtime.install_mineru(
        root,
        run=fake_run,
        network_check=lambda: True,
        verify=lambda target: True,
    )

    assert result["status"] == "success"
    assert len(calls) == 1
    assert root / "runtime" / "optional-site-packages" in [
        root / "runtime" / "optional-site-packages"
    ]
    assert (root / "runtime" / "optional-site-packages" / "mineru").exists()
    assert not (root / "runtime" / "optional-site-packages" / "bin").exists()
    assert not (root / "runtime" / "optional-site-packages.installing").exists()
    log_text = (root / "runtime" / "logs" / "mineru-install.log").read_text(encoding="utf-8")
    assert "installed" in log_text


def test_check_cli_prints_json(monkeypatch, capsys, tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    monkeypatch.setattr(runtime, "probe_runtime", lambda package_root: {"python_ready": True})

    exit_code = runtime.main(["check", "--root", str(root)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"python_ready": True}


def test_check_cli_writes_batch_safe_status_files(monkeypatch, tmp_path: Path):
    runtime = _load_runtime()
    root = _make_package(tmp_path)
    json_output = root / "runtime" / "logs" / "runtime-check.json"
    cmd_output = root / "runtime" / "logs" / "runtime-check.cmd"
    monkeypatch.setattr(
        runtime,
        "probe_runtime",
        lambda package_root: {
            "base_dependencies_ready": False,
            "missing_base_modules": ["uvicorn", "raganything"],
            "mineru_cli_runnable": False,
        },
    )

    exit_code = runtime.main(
        [
            "check",
            "--root",
            str(root),
            "--json-output",
            str(json_output),
            "--cmd-output",
            str(cmd_output),
        ]
    )

    assert exit_code == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["base_dependencies_ready"] is False
    assert cmd_output.read_bytes() == (
        b'set "BASE_READY=0"\r\n'
        b'set "MINERU_READY=0"\r\n'
        b'set "MISSING_BASE_MODULES=uvicorn, raganything"\r\n'
    )


def test_check_url_accepts_healthy_response(monkeypatch):
    runtime = _load_runtime()

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(runtime.urllib.request, "urlopen", lambda url, timeout: Response())

    assert runtime.check_url("http://localhost:8003/health", timeout=2) is True


def test_check_url_cli_returns_failure_without_powershell(monkeypatch):
    runtime = _load_runtime()
    monkeypatch.setattr(runtime, "check_url", lambda url, timeout: False)

    assert runtime.main(["check-url", "http://localhost:8003/health", "--timeout", "2"]) == 1
