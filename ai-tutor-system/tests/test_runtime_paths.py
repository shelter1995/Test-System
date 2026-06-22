import importlib.util
import os
import sys
from pathlib import Path

import pytest


TUTOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TUTOR_ROOT.parent
if str(TUTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(TUTOR_ROOT))


def _runtime_paths_module():
    module_name = "_test_system_tutor_runtime_paths"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, TUTOR_ROOT / "runtime_paths.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module


def _fresh_tutor_config(monkeypatch, **environment):
    names = (
        "TEST_SYSTEM_DATA_DIR",
        "TEST_SYSTEM_TUTOR_DATA_DIR",
        "TEST_SYSTEM_GENERATION_OUTPUT_DIR",
        "TEST_SYSTEM_LOG_DIR",
        "TUTOR_SERVICE_PORT",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, str(value))

    module_name = f"_test_tutor_config_{id(environment)}"
    spec = importlib.util.spec_from_file_location(module_name, TUTOR_ROOT / "tutor_config.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


def test_resolve_runtime_paths_uses_absolute_overrides(tmp_path):
    runtime_paths = _runtime_paths_module()
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


def test_resolve_runtime_paths_falls_back_to_source_layout(tmp_path):
    resolve_runtime_paths = _runtime_paths_module().resolve_runtime_paths

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
def test_resolve_runtime_paths_rejects_relative_overrides(name, tmp_path):
    resolve_runtime_paths = _runtime_paths_module().resolve_runtime_paths

    with pytest.raises(ValueError, match=name):
        resolve_runtime_paths({name: "relative/path"}, source_root=tmp_path)


def test_default_runtime_paths_use_repository_root():
    get_runtime_paths = _runtime_paths_module().get_runtime_paths

    paths = get_runtime_paths()

    assert paths.tutor_data == (REPO_ROOT / "ai-tutor-system" / "tutor_data").resolve()
    assert paths.generation_output == (REPO_ROOT / "generation_output").resolve()
    assert paths.logs == (REPO_ROOT / "runtime" / "logs").resolve()


def test_tutor_config_uses_data_dir_env_file(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    env_path = data_dir / "config" / "tutor.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("TUTOR_SERVICE_PORT=8124\n", encoding="utf-8")

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
