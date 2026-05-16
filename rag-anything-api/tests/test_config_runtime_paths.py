import os

import config


def test_ensure_python_scripts_on_path_adds_executable_dir(monkeypatch, tmp_path):
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    python_exe = scripts_dir / "python.exe"
    python_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("PATH", "")

    result = config._ensure_python_scripts_on_path(str(python_exe))

    assert result == str(scripts_dir)
    assert os.environ["PATH"].split(os.pathsep)[0] == str(scripts_dir)


def test_ensure_python_scripts_on_path_is_idempotent(monkeypatch, tmp_path):
    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    python_exe = scripts_dir / "python.exe"
    python_exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(scripts_dir))

    config._ensure_python_scripts_on_path(str(python_exe))

    assert os.environ["PATH"].split(os.pathsep).count(str(scripts_dir)) == 1
