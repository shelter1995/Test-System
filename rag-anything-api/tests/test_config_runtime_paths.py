import importlib.util
import os
import shutil
import sys
from pathlib import Path

import config
import pytest


API_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MODULE_PREFIX = "_test_system_rag_runtime_paths_"


@pytest.fixture
def runtime_paths_module():
    module_name = "_test_rag_runtime_paths_direct"
    spec = importlib.util.spec_from_file_location(module_name, API_ROOT / "runtime_paths.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module


def _fresh_config(monkeypatch, **environment):
    names = (
        "TEST_SYSTEM_DATA_DIR",
        "TEST_SYSTEM_RAG_STORAGE_DIR",
        "TEST_SYSTEM_RAG_OUTPUT_DIR",
        "RAG_SERVICE_PORT",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, str(value))

    module_name = f"_test_rag_config_{id(environment)}"
    spec = importlib.util.spec_from_file_location(module_name, API_ROOT / "config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_absolute_env_path_uses_override_and_fallback(tmp_path, runtime_paths_module):
    absolute_env_path = runtime_paths_module.absolute_env_path

    override = tmp_path / "override"
    fallback = tmp_path / "fallback"

    assert absolute_env_path("DATA", fallback, {"DATA": str(override)}) == override.resolve()
    assert absolute_env_path("DATA", fallback, {"DATA": ""}) == fallback.resolve()


def test_absolute_env_path_rejects_relative_override(tmp_path, runtime_paths_module):
    absolute_env_path = runtime_paths_module.absolute_env_path

    with pytest.raises(ValueError, match="DATA"):
        absolute_env_path("DATA", tmp_path, {"DATA": "relative/path"})


def test_runtime_roots_use_absolute_overrides(monkeypatch, tmp_path):
    storage = tmp_path / "rag-storage"
    output = tmp_path / "rag-output"

    fresh = _fresh_config(
        monkeypatch,
        TEST_SYSTEM_RAG_STORAGE_DIR=storage,
        TEST_SYSTEM_RAG_OUTPUT_DIR=output,
    )

    assert fresh.STORAGE_ROOT == storage.resolve()
    assert fresh.DATABASE_REGISTRY_FILE == storage.resolve() / "databases.json"
    assert fresh.TRADITIONAL_RAG_STORAGE_ROOT == storage.resolve() / "traditional_rag"
    assert fresh.RAGANYTHING_OUTPUT_ROOT == output.resolve()


def test_runtime_roots_fall_back_to_source_tree(monkeypatch):
    fresh = _fresh_config(monkeypatch)

    assert fresh.STORAGE_ROOT == (API_ROOT / "storage").resolve()
    assert fresh.RAGANYTHING_OUTPUT_ROOT == (API_ROOT / "output").resolve()


def test_config_rejects_relative_runtime_root(monkeypatch):
    with pytest.raises(ValueError, match="TEST_SYSTEM_RAG_STORAGE_DIR"):
        _fresh_config(monkeypatch, TEST_SYSTEM_RAG_STORAGE_DIR="relative/storage")


def test_data_dir_rag_env_takes_priority(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "rag.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("RAG_SERVICE_PORT=8123\n", encoding="utf-8")

    fresh = _fresh_config(
        monkeypatch,
        TEST_SYSTEM_DATA_DIR=data_dir,
        TEST_SYSTEM_RAG_STORAGE_DIR=tmp_path / "storage",
        TEST_SYSTEM_RAG_OUTPUT_DIR=tmp_path / "output",
    )

    assert fresh.ENV_PATH == env_path.resolve()
    assert fresh.RAG_SERVICE_PORT == 8123


def test_source_env_is_fallback_when_data_dir_is_unset(monkeypatch):
    fresh = _fresh_config(monkeypatch)

    assert fresh.ENV_PATH == (API_ROOT / ".env").resolve()


def test_runtime_loader_isolated_between_rag_checkouts(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_SYSTEM_RAG_STORAGE_DIR", raising=False)
    monkeypatch.delenv("TEST_SYSTEM_RAG_OUTPUT_DIR", raising=False)
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    loaded = []
    try:
        for number in (1, 2):
            api_dir = tmp_path / f"checkout-{number}" / "rag-anything-api"
            api_dir.mkdir(parents=True)
            shutil.copy2(API_ROOT / "runtime_paths.py", api_dir / "runtime_paths.py")
            shutil.copy2(API_ROOT / "config.py", api_dir / "config.py")
            spec = importlib.util.spec_from_file_location(
                f"_test_rag_config_checkout_{number}",
                api_dir / "config.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded.append(module)

        assert loaded[0].runtime_paths_module is not loaded[1].runtime_paths_module
        assert loaded[0].STORAGE_ROOT == (tmp_path / "checkout-1" / "rag-anything-api" / "storage").resolve()
        assert loaded[1].STORAGE_ROOT == (tmp_path / "checkout-2" / "rag-anything-api" / "storage").resolve()
    finally:
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)


def test_rag_runtime_loader_rolls_back_failed_module(tmp_path):
    api_dir = tmp_path / "broken" / "rag-anything-api"
    api_dir.mkdir(parents=True)
    shutil.copy2(API_ROOT / "config.py", api_dir / "config.py")
    (api_dir / "runtime_paths.py").write_text("raise RuntimeError('broken rag paths')\n", encoding="utf-8")
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    spec = importlib.util.spec_from_file_location("_test_rag_config_broken", api_dir / "config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        with pytest.raises(RuntimeError, match="broken rag paths"):
            spec.loader.exec_module(module)

        assert {
            name for name in sys.modules if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before
        } == set()
    finally:
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)


def test_rag_dotenv_does_not_override_os_sentinel(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "rag.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("RAG_SERVICE_PORT=8123\n", encoding="utf-8")

    fresh = _fresh_config(
        monkeypatch,
        TEST_SYSTEM_DATA_DIR=data_dir,
        TEST_SYSTEM_RAG_STORAGE_DIR=tmp_path / "storage",
        TEST_SYSTEM_RAG_OUTPUT_DIR=tmp_path / "output",
        RAG_SERVICE_PORT=9002,
    )

    assert fresh.RAG_SERVICE_PORT == 9002


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
