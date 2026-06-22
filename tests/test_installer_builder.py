from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace
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
    _write(root / ".git" / "config", "excluded")
    _write(root / "generation_output" / "result.txt", "excluded")
    _write(root / "docs" / "superpowers" / "secret.md", "excluded")
    _write(root / "ai-tutor-system" / "app.py")
    _write(root / "ai-tutor-system" / ".env.example", "API_KEY=\nSAFE=true\n")
    _write(root / "ai-tutor-system" / "tests" / "test_app.py")
    _write(root / "ai-tutor-system" / "tutor_data" / "private.json")
    _write(root / "rag-anything-api" / "api.py")
    _write(root / "rag-anything-api" / ".env.example", "SECRET=\n")
    _write(root / "rag-anything-api" / "output" / "result.txt", "excluded")
    _write(root / "rag-anything-api" / "storage" / "output" / "result.txt")
    _write(root / "assets" / "logo.txt")
    _write(root / "models" / "cache" / "model.bin")
    _write(root / "dist" / "old.bin")
    _write(root / "build" / "generated.txt", "excluded")
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


def _tracked_files(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def _configure_builder(builder, root: Path) -> None:
    tracked = _tracked_files(root)
    builder.collect_tracked_files = lambda candidate: tracked
    builder._resolve_uv_executable = lambda candidate: candidate or "fake-uv.exe"


def _build(tmp_path: Path, **overrides) -> Path:
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
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
        ".git/config",
        "generation_output/result.txt",
        "docs",
        "ai-tutor-system/tests",
        "ai-tutor-system/tutor_data",
        "rag-anything-api/storage/output",
        "rag-anything-api/output/result.txt",
        "models",
        "dist",
        "build/generated.txt",
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


def test_install_image_copies_only_tracked_business_files(tmp_path: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    tracked = _tracked_files(root)
    untracked = (
        Path("ai-tutor-system/.env.local"),
        Path("assets/client.cert"),
        Path("rag-anything-api/credentials.json"),
        Path("ai-tutor-system/outputs/private.txt"),
        Path("rag-anything-api/tmp/private.txt"),
    )
    for relative in untracked:
        _write(root / relative, "untracked secret")
    builder.collect_tracked_files = lambda candidate: tracked
    builder._resolve_uv_executable = lambda candidate: "fake-uv.exe"

    stage = builder.build_install_image(
        root,
        tmp_path / "output",
        python_home,
        desktop_publish,
        uv_executable="fake-uv.exe",
    )

    assert (stage / "ai-tutor-system/.env.example").exists()
    assert (stage / "ai-tutor-system/.env").exists()
    for relative in untracked:
        assert not (stage / relative).exists(), relative


def test_collect_tracked_files_fails_when_git_listing_fails(tmp_path: Path, monkeypatch):
    builder = _load_builder()

    def failed_git(command, **kwargs):
        return subprocess.CompletedProcess(command, 128, stdout=b"", stderr=b"not a repository")

    monkeypatch.setattr(builder.subprocess, "run", failed_git)

    with pytest.raises(RuntimeError, match="git ls-files"):
        builder.collect_tracked_files(tmp_path)


def test_collect_tracked_files_parses_nul_delimited_output(tmp_path: Path, monkeypatch):
    builder = _load_builder()

    def listed_git(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"assets/logo.png\0ai-tutor-system/app.py\0",
            stderr=b"",
        )

    monkeypatch.setattr(builder.subprocess, "run", listed_git)

    assert builder.collect_tracked_files(tmp_path) == {
        Path("assets/logo.png"),
        Path("ai-tutor-system/app.py"),
    }


def test_install_image_rejects_tracked_symlink_outside_source(tmp_path: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    external = tmp_path / "external-secret.txt"
    _write(external, "secret")
    link = root / "assets" / "external-secret.txt"
    try:
        link.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    tracked = _tracked_files(root) | {link.relative_to(root)}
    builder.collect_tracked_files = lambda candidate: tracked
    builder._resolve_uv_executable = lambda candidate: "fake-uv.exe"

    with pytest.raises(ValueError, match="symlink|reparse"):
        builder.build_install_image(
            root,
            tmp_path / "output",
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )


def test_reparse_detector_recognizes_windows_reparse_attribute():
    builder = _load_builder()
    fake_path = SimpleNamespace(
        is_symlink=lambda: False,
        lstat=lambda: SimpleNamespace(st_file_attributes=0x400),
    )

    assert builder.is_reparse_point(fake_path)


def test_standard_root_build_installer_output_is_allowed(tmp_path: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)

    stage = builder.build_install_image(
        root,
        root / ".build" / "installer",
        python_home,
        desktop_publish,
        uv_executable="fake-uv.exe",
    )

    assert stage == root / ".build" / "installer" / "Test-System"


def test_public_builder_resolves_default_version_once_for_relative_root(
    tmp_path: Path, monkeypatch
):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    monkeypatch.chdir(tmp_path)

    stage = builder.build_install_image(
        Path("source"),
        tmp_path / "output",
        python_home,
        desktop_publish,
        uv_executable="fake-uv.exe",
    )

    manifest = json.loads(
        (stage / "runtime" / "install-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["product"]["version"] == "2.3.4"


def test_cli_resolves_default_version_once_for_relative_root(
    tmp_path: Path, monkeypatch, capsys
):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "installer_builder.py",
            "--root",
            "source",
            "--output-root",
            str(tmp_path / "output"),
            "--python-home",
            str(python_home),
            "--desktop-publish",
            str(desktop_publish),
            "--uv-executable",
            "fake-uv.exe",
        ],
    )

    builder.main()

    stage = tmp_path / "output" / "Test-System"
    manifest = json.loads(
        (stage / "runtime" / "install-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["product"]["version"] == "2.3.4"
    assert "Install image created:" in capsys.readouterr().out


@pytest.mark.parametrize("source_name", ["assets", "packaging"])
def test_output_inside_copied_source_is_rejected_before_creation(
    tmp_path: Path, source_name: str
):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = root / source_name / "installer-output"

    with pytest.raises(ValueError, match="overlap"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert not output_root.exists()


@pytest.mark.parametrize("overlap", ["desktop", "python"])
def test_runtime_inputs_cannot_overlap_target(tmp_path: Path, overlap: str):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    if overlap == "desktop":
        desktop_publish = target
        _write(desktop_publish / "TestSystem.exe", "host")
    else:
        python_home = target
        _write(python_home / "python.exe", "python")
    _write(target / "marker.txt", "preserve")

    with pytest.raises(ValueError, match="overlap"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert (target / "marker.txt").exists()


@pytest.mark.parametrize(
    "collision",
    [Path("version.json"), Path("runtime/host.dll"), Path("README.md")],
)
def test_desktop_publish_reserved_names_are_rejected(tmp_path: Path, collision: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    _write(desktop_publish / collision, "collision")

    with pytest.raises(ValueError, match="reserved|collision"):
        builder.build_install_image(
            root,
            tmp_path / "output",
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )


def test_desktop_publish_empty_reserved_directory_is_rejected(tmp_path: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    (desktop_publish / "runtime").mkdir()

    with pytest.raises(ValueError, match="reserved"):
        builder.build_install_image(
            root,
            tmp_path / "output",
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )


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
    assert not (rebuilt / "runtime" / "logs" / "bootstrap.log").exists()


def test_failed_dependency_install_keeps_external_build_log_and_old_target(tmp_path: Path):
    builder = _load_builder()
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    _write(target / "installed.txt", "old")

    def failed_install(command, **kwargs):
        if command[1:2] == ["-c"]:
            return _fake_run(command, **kwargs)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="https://user:password@example.invalid/simple",
            stderr=str(python_home),
        )

    builder._run = failed_install

    with pytest.raises(RuntimeError, match="Base dependency installation failed"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    log_path = output_root / "build-logs" / "bootstrap.log"
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "user" not in log_text
    assert "password" not in log_text
    assert str(python_home) not in log_text
    assert (target / "installed.txt").exists()
    assert not list(output_root.glob(".Test-System.building-*"))


@pytest.mark.parametrize("uv_state", ["missing", "directory"])
def test_installer_rejects_uv_executable_that_is_not_a_file(tmp_path: Path, uv_state: str):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    tracked = _tracked_files(root)
    builder.collect_tracked_files = lambda candidate: tracked
    uv_path = tmp_path / "uv.exe"
    if uv_state == "directory":
        uv_path.mkdir()

    with pytest.raises(FileNotFoundError, match="uv executable"):
        builder.build_install_image(
            root,
            tmp_path / "output",
            python_home,
            desktop_publish,
            uv_executable=str(uv_path),
        )


def test_cli_reports_build_error_without_traceback(tmp_path: Path, monkeypatch, capsys):
    builder = _load_builder()

    def fail_build(*args, **kwargs):
        raise ValueError("unsafe topology")

    monkeypatch.setattr(builder, "_build_install_image", fail_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "installer_builder.py",
            "--output-root",
            str(tmp_path / "output"),
            "--python-home",
            str(tmp_path / "python"),
            "--desktop-publish",
            str(tmp_path / "desktop"),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        builder.main()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert captured.out == ""
    assert "error: unsafe topology" in captured.err
    assert "Traceback" not in captured.err


def test_cli_keeps_argparse_errors_at_exit_code_2(monkeypatch, capsys):
    builder = _load_builder()
    monkeypatch.setattr(sys, "argv", ["installer_builder.py"])

    with pytest.raises(SystemExit) as exc_info:
        builder.main()

    assert exc_info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_concurrent_build_lock_preserves_target_and_unowned_staging(tmp_path: Path):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    unowned_stage = output_root / ".Test-System.building-stale"
    _write(target / "installed.txt", "old")
    _write(unowned_stage / "owner.txt", "other build")
    _write(output_root / ".Test-System.lock", "other build")

    with pytest.raises(RuntimeError, match="another installer build is already running"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert (target / "installed.txt").read_text(encoding="utf-8") == "old"
    assert (unowned_stage / "owner.txt").read_text(encoding="utf-8") == "other build"


def test_unique_staging_collision_does_not_delete_unowned_directory(tmp_path: Path, monkeypatch):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = tmp_path / "output"
    unowned_stage = output_root / ".Test-System.building-forced-collision"
    _write(unowned_stage / "owner.txt", "other process")
    monkeypatch.setattr(
        builder.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="forced-collision"),
    )

    with pytest.raises(FileExistsError):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert (unowned_stage / "owner.txt").read_text(encoding="utf-8") == "other process"


def test_failed_stage_promotion_restores_previous_target(tmp_path: Path, monkeypatch):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
    output_root = tmp_path / "output"
    target = output_root / "Test-System"
    _write(target / "installed.txt", "old")

    def fail_stage_promotion(source: Path, destination: Path) -> None:
        if ".building-" in source.name and destination == target:
            raise OSError("simulated promotion failure")
        source.replace(destination)

    monkeypatch.setattr(builder, "_replace_path", fail_stage_promotion, raising=False)

    with pytest.raises(OSError, match="simulated promotion failure"):
        builder.build_install_image(
            root,
            output_root,
            python_home,
            desktop_publish,
            uv_executable="fake-uv.exe",
        )

    assert (target / "installed.txt").read_text(encoding="utf-8") == "old"
    assert not list(output_root.glob(".Test-System.building-*"))
    assert not list(output_root.glob(".Test-System.backup-*"))


@pytest.mark.parametrize("host_state", ["missing-directory", "missing-executable"])
def test_install_image_rejects_missing_desktop_host_and_preserves_target(
    tmp_path: Path, host_state: str
):
    builder = _load_builder()
    builder._run = _fake_run
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
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

    assert (target / "stale-success.txt").exists()


def test_install_image_rejects_invalid_python_and_preserves_target(tmp_path: Path):
    builder = _load_builder()
    root, python_home, desktop_publish = _source_tree(tmp_path)
    _configure_builder(builder, root)
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

    assert (target / "stale-success.txt").exists()
