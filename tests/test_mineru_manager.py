from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


def _load_manager():
    module_path = Path(__file__).resolve().parents[1] / "packaging" / "mineru_manager.py"
    spec = importlib.util.spec_from_file_location("mineru_manager", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_layout(tmp_path: Path) -> tuple[Path, Path]:
    package_root = tmp_path / "InstallDir"
    data_root = tmp_path / "DataDir"
    (package_root / "runtime" / "python").mkdir(parents=True)
    (package_root / "runtime" / "python" / "python.exe").write_text("stub", encoding="utf-8")
    (package_root / "runtime" / "site-packages").mkdir(parents=True)
    (package_root / "packaging").mkdir(parents=True)
    (package_root / "packaging" / "mineru-requirements.txt").write_text(
        "mineru[core]==3.3.1\n"
        "torch<3,>=2.6.0\n"
        "transformers<5.0.0,>=4.57.3\n",
        encoding="utf-8",
    )
    (data_root / "runtime" / "optional-site-packages").mkdir(parents=True)
    (data_root / "models" / "mineru").mkdir(parents=True)
    return package_root, data_root


def test_install_command_uses_bundled_python_target_and_pinned_requirements(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)

    paths = manager.MineruPaths(package_root, data_root)
    command = manager.build_pip_install_command(paths)

    assert command[:4] == [str(package_root / "runtime" / "python" / "python.exe"), "-m", "pip", "install"]
    assert command[command.index("--target") + 1] == str(
        data_root / "runtime" / "optional-site-packages.installing"
    )
    assert command[command.index("--requirement") + 1] == str(
        package_root / "packaging" / "mineru-requirements.txt"
    )
    assert "--upgrade" not in command
    assert "-U" not in command


def test_model_download_command_uses_modelscope_pipeline(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)

    command = manager.build_model_download_command(manager.MineruPaths(package_root, data_root), "modelscope")

    assert command == [
        str(package_root / "runtime" / "python" / "python.exe"),
        "-m",
        "mineru.cli.models_download",
        "--source",
        "modelscope",
        "--model_type",
        "pipeline",
    ]


def test_whisper_model_download_command_uses_data_root_cache(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)

    command = manager.build_whisper_model_download_command(paths)

    assert command[:2] == [str(package_root / "runtime" / "python" / "python.exe"), "-c"]
    assert "whisper.load_model" in command[-1]
    assert "WHISPER_CACHE_DIR" in command[-1]
    assert "WHISPER_MODEL" in command[-1]


def test_environment_prefers_installing_packages_and_keeps_caches_under_data_root(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)

    env = manager.build_install_environment(
        manager.MineruPaths(package_root, data_root),
        use_installing=True,
        base_env={"PYTHONPATH": "existing"},
    )

    pythonpath = env["PYTHONPATH"].split(os.pathsep)
    assert pythonpath[:2] == [
        str(data_root / "runtime" / "optional-site-packages.installing"),
        str(package_root / "rag-anything-api"),
    ]
    assert str(data_root / "runtime" / "optional-site-packages") not in pythonpath
    assert str(package_root / "runtime" / "site-packages") not in pythonpath
    assert str(package_root / "runtime" / "site-packages.installing") not in pythonpath
    assert env["HF_HOME"] == str(data_root / "models" / "mineru" / "huggingface")
    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"
    assert env["HUGGINGFACE_HUB_CACHE"] == str(data_root / "models" / "mineru" / "huggingface" / "hub")
    assert env["MODELSCOPE_CACHE"] == str(data_root / "models" / "mineru" / "modelscope")
    assert env["MINERU_TOOLS_CONFIG_JSON"] == str(data_root / "models" / "mineru" / "mineru.json")
    assert env["WHISPER_CACHE_DIR"] == str(data_root / "models" / "whisper")
    assert env["WHISPER_MODEL"] == "base"


def test_environment_normalizes_inherited_invalid_hf_endpoint(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)

    env = manager.build_install_environment(
        manager.MineruPaths(package_root, data_root),
        use_installing=True,
        base_env={"HF_ENDPOINT": "/api"},
    )

    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"


def test_environment_preserves_inherited_http_hf_endpoint(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)

    env = manager.build_install_environment(
        manager.MineruPaths(package_root, data_root),
        use_installing=True,
        base_env={"HF_ENDPOINT": "https://hf-mirror.com/"},
    )

    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"


def test_environment_filters_inherited_pythonpath_that_could_contaminate_install_verification(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    unrelated = tmp_path / "safe-extra"
    inherited = os.pathsep.join(
        [
            str(paths.current_target),
            str(paths.current_target / "nested"),
            str(paths.package_site_packages),
            str(paths.installing_target),
            str(unrelated),
        ]
    )

    env = manager.build_install_environment(paths, use_installing=True, base_env={"PYTHONPATH": inherited})

    pythonpath = env["PYTHONPATH"].split(os.pathsep)
    assert str(paths.current_target) not in pythonpath
    assert str(paths.current_target / "nested") not in pythonpath
    assert str(paths.package_site_packages) not in pythonpath
    assert pythonpath.count(str(paths.installing_target)) == 1
    assert str(unrelated) in pythonpath


def test_successful_verification_requires_version_cli_downloader_help_and_model_file(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    (paths.installing_target / "mineru" / "cli").mkdir(parents=True)
    (paths.models_root / "modelscope").mkdir(parents=True)
    (paths.models_root / "modelscope" / "weights.bin").write_bytes(b"model")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        assert kwargs["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(paths.installing_target)
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, stdout="usage", stderr="")
        code = command[-1] if command[:2] == [str(paths.python_exe), "-c"] else ""
        if "import whisper" in code:
            return subprocess.CompletedProcess(command, 0, stdout="media-deps-ok", stderr="")
        if "fast_langdetect" in code:
            return subprocess.CompletedProcess(command, 0, stdout="fast-langdetect-ok", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="3.3.1\nclient-main-ok", stderr="")

    assert manager.verify_installation(paths, run=fake_run) is True
    assert any(call[-1] == "--help" for call in calls)


def test_verification_requires_media_dependencies(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    (paths.models_root / "modelscope").mkdir(parents=True)
    (paths.models_root / "modelscope" / "weights.bin").write_bytes(b"model")
    snippets = []

    def fake_run(command, **kwargs):
        code = command[-1] if command[:2] == [str(paths.python_exe), "-c"] else ""
        snippets.append(code)
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, stdout="usage", stderr="")
        if "import whisper" in code:
            return subprocess.CompletedProcess(command, 0, stdout="media-deps-ok", stderr="")
        if "fast_langdetect" in code:
            return subprocess.CompletedProcess(command, 0, stdout="fast-langdetect-ok", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="3.3.1\nclient-main-ok", stderr="")

    assert manager.verify_installation(paths, run=fake_run) is True
    assert any("imageio_ffmpeg" in snippet for snippet in snippets)
    assert any("import whisper" in snippet for snippet in snippets)
    assert any("fast_langdetect" in snippet for snippet in snippets)


def test_verification_rejects_missing_media_dependencies(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    (paths.models_root / "weights.bin").write_bytes(b"model")

    def fake_run(command, **kwargs):
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, stdout="usage", stderr="")
        code = command[-1] if command[:2] == [str(paths.python_exe), "-c"] else ""
        if "import whisper" in code:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="missing")
        return subprocess.CompletedProcess(command, 0, stdout="3.3.1\nclient-main-ok", stderr="")

    assert manager.verify_installation(paths, run=fake_run) is False


def test_verification_rejects_missing_fast_langdetect_resource(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    (paths.models_root / "weights.bin").write_bytes(b"model")

    def fake_run(command, **kwargs):
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, stdout="usage", stderr="")
        code = command[-1] if command[:2] == [str(paths.python_exe), "-c"] else ""
        if "import whisper" in code:
            return subprocess.CompletedProcess(command, 0, stdout="media-deps-ok", stderr="")
        if "fast_langdetect" in code:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="lid.176.ftz cannot be opened")
        return subprocess.CompletedProcess(command, 0, stdout="3.3.1\nclient-main-ok", stderr="")

    assert manager.verify_installation(paths, run=fake_run) is False


def test_verification_rejects_wrong_distribution_version_even_with_models(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    paths.models_root.mkdir(parents=True, exist_ok=True)
    (paths.models_root / "weights.bin").write_bytes(b"model")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="3.3.0\nclient-main-ok", stderr="")

    assert manager.verify_installation(paths, run=fake_run) is False


@pytest.mark.parametrize("failed_stage", ["pip", "verify", "models"])
def test_failed_stages_keep_current_packages_remove_installing_retain_models_and_write_status(
    tmp_path: Path,
    failed_stage: str,
):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    status_json = data_root / "runtime" / "mineru-status.json"
    (paths.current_target / "keep.txt").write_text("current", encoding="utf-8")
    (paths.models_root / "cache.bin").write_bytes(b"keep-model-cache")

    def fake_run(command, **kwargs):
        if "-m" in command and command[command.index("-m") + 1] == "pip":
            paths.installing_target.mkdir(parents=True, exist_ok=True)
            (paths.installing_target / "new.txt").write_text("new", encoding="utf-8")
            return subprocess.CompletedProcess(command, 1 if failed_stage == "pip" else 0, stdout="", stderr="boom")
        if "-m" in command and command[command.index("-m") + 1] == "mineru.cli.models_download":
            return subprocess.CompletedProcess(command, 1 if failed_stage == "models" else 0, stdout="", stderr="boom")
        return subprocess.CompletedProcess(command, 0, stdout="3.3.1\nclient-main-ok", stderr="")

    result = manager.install_mineru(
        package_root,
        data_root,
        source="modelscope",
        status_json=status_json,
        run=fake_run,
        verify=(lambda install_paths, run: failed_stage != "verify"),
        emit_progress=lambda record: None,
    )

    assert result["status"] == "error"
    assert result["stage"] == failed_stage
    assert (paths.current_target / "keep.txt").read_text(encoding="utf-8") == "current"
    assert not paths.installing_target.exists()
    assert (paths.models_root / "cache.bin").read_bytes() == b"keep-model-cache"
    written = json.loads(status_json.read_text(encoding="utf-8"))
    assert written["status"] == "error"
    assert written["stage"] == failed_stage


def test_whisper_model_download_failure_is_nonfatal_and_recorded_as_warning(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    status_json = data_root / "runtime" / "mineru-status.json"
    progress = []

    def fake_run(command, **kwargs):
        if "-m" in command and command[command.index("-m") + 1] == "pip":
            paths.installing_target.mkdir(parents=True, exist_ok=True)
            (paths.installing_target / "new.txt").write_text("new", encoding="utf-8")
        elif "-m" in command and command[command.index("-m") + 1] == "mineru.cli.models_download":
            (paths.models_root / "weights.bin").write_bytes(b"model")
        elif command[:2] == [str(paths.python_exe), "-c"] and "whisper.load_model" in command[-1]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="network failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = manager.install_mineru(
        package_root,
        data_root,
        source="modelscope",
        status_json=status_json,
        run=fake_run,
        verify=lambda install_paths, run: True,
        emit_progress=progress.append,
    )

    assert result["status"] == "success"
    assert any("Whisper" in warning for warning in result["warnings"])
    assert any(item["stage"] == "whisper_models_warning" for item in progress)
    assert (paths.current_target / "new.txt").read_text(encoding="utf-8") == "new"
    written = json.loads(status_json.read_text(encoding="utf-8"))
    assert written["status"] == "success"
    assert written["warnings"] == result["warnings"]


def test_success_rotates_current_to_previous_promotes_installing_and_deletes_backup(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    status_json = data_root / "runtime" / "mineru-status.json"
    (paths.current_target / "old.txt").write_text("old", encoding="utf-8")

    def fake_run(command, **kwargs):
        if "-m" in command and command[command.index("-m") + 1] == "pip":
            paths.installing_target.mkdir(parents=True, exist_ok=True)
            (paths.installing_target / "new.txt").write_text("new", encoding="utf-8")
        elif "-m" in command and command[command.index("-m") + 1] == "mineru.cli.models_download":
            (paths.models_root / "weights.bin").write_bytes(b"model")
        elif command[:2] == [str(paths.python_exe), "-c"] and "whisper.load_model" in command[-1]:
            (paths.whisper_models_root / "base.pt").parent.mkdir(parents=True, exist_ok=True)
            (paths.whisper_models_root / "base.pt").write_bytes(b"whisper-model")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = manager.install_mineru(
        package_root,
        data_root,
        source="modelscope",
        status_json=status_json,
        run=fake_run,
        verify=lambda install_paths, run: True,
        emit_progress=lambda record: None,
    )

    assert result["status"] == "success"
    assert (paths.current_target / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (paths.current_target / "old.txt").exists()
    assert not paths.installing_target.exists()
    assert not paths.previous_target.exists()


def test_lock_file_prevents_concurrent_installs(tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    status_json = data_root / "runtime" / "mineru-status.json"
    paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = manager.acquire_install_lock(paths)
    try:
        result = manager.install_mineru(
            package_root,
            data_root,
            source="modelscope",
            status_json=status_json,
            run=lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
            emit_progress=lambda record: None,
        )
    finally:
        lock_handle.release()

    assert result["status"] == "error"
    assert result["stage"] == "lock"
    assert "已有安装任务" in result["message"]


def test_stale_lock_file_is_removed_before_install(monkeypatch, tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    paths = manager.MineruPaths(package_root, data_root)
    status_json = data_root / "runtime" / "mineru-status.json"
    paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
    paths.lock_path.write_text("999999", encoding="ascii")
    monkeypatch.setattr(manager, "_pid_exists", lambda pid: False)

    result = manager.install_mineru(
        package_root,
        data_root,
        source="modelscope",
        status_json=status_json,
        run=lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout="", stderr=""),
        verify=lambda install_paths, run: True,
        emit_progress=lambda record: None,
    )

    assert result["status"] == "success"
    assert not paths.lock_path.exists()


def test_cli_install_prints_newline_delimited_json_progress(monkeypatch, capsys, tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    status_json = data_root / "runtime" / "mineru-status.json"

    monkeypatch.setattr(
        manager,
        "install_mineru",
        lambda package_root, data_root, source, status_json, emit_progress=print, **kwargs: (
            emit_progress({"stage": "dependencies", "percent": 10, "message": "正在安装增强解析依赖（MinerU / FFmpeg / Whisper）"}),
            emit_progress({"stage": "models", "percent": 60, "message": "正在下载 MinerU 模型"}),
            emit_progress({"stage": "complete", "percent": 100, "message": "增强解析组件安装完成（MinerU / FFmpeg / Whisper）"}),
            {"status": "success", "stage": "complete"},
        )[-1],
    )

    exit_code = manager.main(
        [
            "install",
            "--package-root",
            str(package_root),
            "--data-root",
            str(data_root),
            "--source",
            "modelscope",
            "--status-json",
            str(status_json),
        ]
    )

    assert exit_code == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records == [
        {"stage": "dependencies", "percent": 10, "message": "正在安装增强解析依赖（MinerU / FFmpeg / Whisper）"},
        {"stage": "models", "percent": 60, "message": "正在下载 MinerU 模型"},
        {"stage": "complete", "percent": 100, "message": "增强解析组件安装完成（MinerU / FFmpeg / Whisper）"},
    ]


def test_cli_install_prints_failure_result_for_diagnostics(monkeypatch, capsys, tmp_path: Path):
    manager = _load_manager()
    package_root, data_root = _make_layout(tmp_path)
    status_json = data_root / "runtime" / "mineru-status.json"

    monkeypatch.setattr(
        manager,
        "install_mineru",
        lambda package_root, data_root, source, status_json, emit_progress=print, **kwargs: {
            "status": "error",
            "stage": "verify",
            "message": "MinerU 安装后验证失败",
        },
    )

    exit_code = manager.main(
        [
            "install",
            "--package-root",
            str(package_root),
            "--data-root",
            str(data_root),
            "--source",
            "modelscope",
            "--status-json",
            str(status_json),
        ]
    )

    assert exit_code == 1
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records == [
        {"status": "error", "stage": "verify", "message": "MinerU 安装后验证失败"},
    ]
