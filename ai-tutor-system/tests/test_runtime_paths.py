import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest


TUTOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TUTOR_ROOT.parent
RUNTIME_MODULE_PREFIX = "_test_system_tutor_runtime_paths_"
if str(TUTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(TUTOR_ROOT))


@pytest.fixture(autouse=True)
def clear_runtime_path_caches_after_test():
    yield
    for name, module in list(sys.modules.items()):
        if name.startswith(RUNTIME_MODULE_PREFIX) and hasattr(module, "get_runtime_paths"):
            module.get_runtime_paths.cache_clear()


def _load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runtime_paths_module():
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    module_name = "_test_tutor_runtime_paths_direct"
    spec = importlib.util.spec_from_file_location(module_name, TUTOR_ROOT / "runtime_paths.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        if hasattr(module.get_runtime_paths, "cache_clear"):
            module.get_runtime_paths.cache_clear()
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)
        sys.modules.pop(module_name, None)


def _fresh_tutor_config(monkeypatch, *, clear_cache_after=True, **environment):
    names = (
        "TEST_SYSTEM_DATA_DIR",
        "TEST_SYSTEM_TUTOR_DATA_DIR",
        "TEST_SYSTEM_GENERATION_OUTPUT_DIR",
        "TEST_SYSTEM_LOG_DIR",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, str(value))

    for name, runtime_module in list(sys.modules.items()):
        if name.startswith(RUNTIME_MODULE_PREFIX) and hasattr(runtime_module, "get_runtime_paths"):
            runtime_module.get_runtime_paths.cache_clear()

    module_name = f"_test_tutor_config_{id(environment)}"
    spec = importlib.util.spec_from_file_location(module_name, TUTOR_ROOT / "tutor_config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        if clear_cache_after and hasattr(module, "runtime_paths_module"):
            module.runtime_paths_module.get_runtime_paths.cache_clear()
        sys.modules.pop(module_name, None)


def test_resolve_runtime_paths_uses_absolute_overrides(tmp_path, runtime_paths_module):
    runtime_paths = runtime_paths_module
    RuntimePaths = runtime_paths.RuntimePaths
    resolve_runtime_paths = runtime_paths.resolve_runtime_paths

    paths = resolve_runtime_paths(
        {
            "TEST_SYSTEM_TUTOR_DATA_DIR": str(tmp_path / "tutor"),
            "TEST_SYSTEM_GENERATION_OUTPUT_DIR": str(tmp_path / "output"),
            "TEST_SYSTEM_LOG_DIR": str(tmp_path / "logs"),
        },
        source_root=tmp_path / "source",
    )

    assert isinstance(paths, RuntimePaths)
    assert paths.tutor_data == (tmp_path / "tutor").resolve()
    assert paths.generation_output == (tmp_path / "output").resolve()
    assert paths.logs == (tmp_path / "logs").resolve()


def test_resolve_runtime_paths_falls_back_to_source_layout(tmp_path, runtime_paths_module):
    resolve_runtime_paths = runtime_paths_module.resolve_runtime_paths

    paths = resolve_runtime_paths({}, source_root=tmp_path)

    assert paths.tutor_data == (tmp_path / "ai-tutor-system" / "tutor_data").resolve()
    assert paths.generation_output == (tmp_path / "generation_output").resolve()
    assert paths.logs == (tmp_path / "runtime" / "logs").resolve()


@pytest.mark.parametrize(
    "name",
    [
        "TEST_SYSTEM_TUTOR_DATA_DIR",
        "TEST_SYSTEM_GENERATION_OUTPUT_DIR",
        "TEST_SYSTEM_LOG_DIR",
    ],
)
def test_resolve_runtime_paths_rejects_relative_overrides(name, tmp_path, runtime_paths_module):
    resolve_runtime_paths = runtime_paths_module.resolve_runtime_paths

    with pytest.raises(ValueError, match=name):
        resolve_runtime_paths({name: "relative/path"}, source_root=tmp_path)


def test_default_runtime_paths_use_repository_root(runtime_paths_module):
    get_runtime_paths = runtime_paths_module.get_runtime_paths

    paths = get_runtime_paths()

    assert paths.tutor_data == (REPO_ROOT / "ai-tutor-system" / "tutor_data").resolve()
    assert paths.generation_output == (REPO_ROOT / "generation_output").resolve()
    assert paths.logs == (REPO_ROOT / "runtime" / "logs").resolve()


def test_tutor_config_uses_data_dir_env_file(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "tutor.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("TUTOR_SERVICE_PORT=8124\n", encoding="utf-8")
    monkeypatch.delenv("TUTOR_SERVICE_PORT", raising=False)

    fresh = _fresh_tutor_config(
        monkeypatch,
        TEST_SYSTEM_DATA_DIR=data_dir,
        TEST_SYSTEM_TUTOR_DATA_DIR=tmp_path / "tutor-data",
    )

    assert Path(fresh.ENV_PATH) == env_path.resolve()
    assert fresh.TUTOR_SERVICE_PORT == 8124
    assert Path(fresh.DATA_DIR) == (tmp_path / "tutor-data").resolve()
    assert Path(fresh.SCENARIOS_FILE) == (tmp_path / "tutor-data" / "scenarios.json").resolve()


def test_tutor_config_falls_back_to_source_env(monkeypatch):
    fresh = _fresh_tutor_config(monkeypatch)

    assert Path(fresh.ENV_PATH) == (TUTOR_ROOT / ".env").resolve()


def test_runtime_loader_isolated_between_checkouts(monkeypatch, tmp_path):
    monkeypatch.delenv("TEST_SYSTEM_TUTOR_DATA_DIR", raising=False)
    monkeypatch.delenv("TEST_SYSTEM_GENERATION_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("TEST_SYSTEM_LOG_DIR", raising=False)
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    loaded_modules = []
    try:
        for number in (1, 2):
            tutor_dir = tmp_path / f"checkout-{number}" / "ai-tutor-system"
            tutor_dir.mkdir(parents=True)
            shutil.copy2(TUTOR_ROOT / "runtime_paths.py", tutor_dir / "runtime_paths.py")
            shutil.copy2(TUTOR_ROOT / "generation_api.py", tutor_dir / "generation_api.py")
            loaded_modules.append(
                _load_module(f"_test_generation_api_checkout_{number}", tutor_dir / "generation_api.py")
            )

        first_paths = loaded_modules[0].get_runtime_paths()
        second_paths = loaded_modules[1].get_runtime_paths()

        assert loaded_modules[0].runtime_paths_module is not loaded_modules[1].runtime_paths_module
        assert first_paths.generation_output == (tmp_path / "checkout-1" / "generation_output").resolve()
        assert second_paths.generation_output == (tmp_path / "checkout-2" / "generation_output").resolve()
    finally:
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)


def test_runtime_loader_rolls_back_failed_module(monkeypatch, tmp_path):
    tutor_dir = tmp_path / "broken" / "ai-tutor-system"
    tutor_dir.mkdir(parents=True)
    shutil.copy2(TUTOR_ROOT / "generation_api.py", tutor_dir / "generation_api.py")
    (tutor_dir / "runtime_paths.py").write_text("raise RuntimeError('broken runtime paths')\n", encoding="utf-8")
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    try:
        with pytest.raises(RuntimeError, match="broken runtime paths"):
            _load_module("_test_generation_api_broken", tutor_dir / "generation_api.py")

        assert {
            name for name in sys.modules if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before
        } == set()
    finally:
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)


def test_runtime_paths_are_cached_across_tutor_modules(monkeypatch, tmp_path):
    import generation_api
    import generation_runner

    first_root = tmp_path / "first-output"
    second_root = tmp_path / "second-output"
    fresh_config = _fresh_tutor_config(
        monkeypatch,
        clear_cache_after=False,
        TEST_SYSTEM_GENERATION_OUTPUT_DIR=first_root,
    )
    runtime_paths = fresh_config.runtime_paths_module
    try:
        first = fresh_config.RUNTIME_PATHS
        monkeypatch.setenv("TEST_SYSTEM_GENERATION_OUTPUT_DIR", str(second_root))

        assert generation_runner.runtime_paths_module is runtime_paths
        assert generation_api.runtime_paths_module is runtime_paths
        assert fresh_config.RUNTIME_PATHS is first
        assert generation_api.get_runtime_paths() is first
        assert generation_runner.get_runtime_paths() is first
        assert generation_api.get_runtime_paths().generation_output == first_root.resolve()
    finally:
        runtime_paths.get_runtime_paths.cache_clear()


def test_first_runtime_snapshot_loads_tutor_dotenv(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    tutor_dir = checkout / "ai-tutor-system"
    tutor_dir.mkdir(parents=True)
    shutil.copy2(TUTOR_ROOT / "runtime_paths.py", tutor_dir / "runtime_paths.py")
    shutil.copy2(TUTOR_ROOT / "generation_api.py", tutor_dir / "generation_api.py")
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "tutor.env"
    env_path.parent.mkdir(parents=True)
    output_dir = tmp_path / "dotenv-output"
    env_path.write_text(
        f"TEST_SYSTEM_GENERATION_OUTPUT_DIR={output_dir}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_SYSTEM_DATA_DIR", str(data_dir))
    monkeypatch.delenv("TEST_SYSTEM_GENERATION_OUTPUT_DIR", raising=False)
    before = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith(RUNTIME_MODULE_PREFIX)
    }
    try:
        generation_api = _load_module("_test_generation_api_dotenv", tutor_dir / "generation_api.py")

        assert generation_api.get_runtime_paths().generation_output == output_dir.resolve()
    finally:
        for name in list(sys.modules):
            if name.startswith(RUNTIME_MODULE_PREFIX) and name not in before:
                sys.modules.pop(name, None)
        sys.modules.update(before)


def test_tutor_dotenv_does_not_override_os_sentinel(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "tutor.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("TUTOR_SERVICE_PORT=8124\n", encoding="utf-8")
    monkeypatch.setenv("TUTOR_SERVICE_PORT", "9001")

    fresh = _fresh_tutor_config(monkeypatch, TEST_SYSTEM_DATA_DIR=data_dir)

    assert fresh.TUTOR_SERVICE_PORT == 9001
