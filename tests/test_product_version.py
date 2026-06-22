from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "packaging" / "product_version.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("product_version", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_version_file_is_exactly_initial_product_version():
    payload = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    assert payload == {"version": "1.0.0"}


def test_read_product_version_exposes_numeric_components(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "version.json"
    source.write_text('{"version":"2.3.4"}', encoding="utf-8")

    version = module.read_product_version(source)

    assert version.text == "2.3.4"
    assert (version.major, version.minor, version.patch) == (2, 3, 4)
    assert version.file_version == "2.3.4.0"


@pytest.mark.parametrize(
    "payload",
    [
        {"version": "1.0.0-beta"},
        {"version": "1.0.0", "other": 1},
        [],
        "1.0.0",
        1,
        None,
        {"version": 1},
        {"version": None},
        {"version": "1.2"},
        {"version": "1.2.3.4"},
        {"version": "v1.2.3"},
    ],
)
def test_read_product_version_rejects_invalid_contract(tmp_path: Path, payload):
    module = _load_module()
    source = tmp_path / "version.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        module.read_product_version(source)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], "1.0.0"),
        (["--field", "major"], "1"),
        (["--field", "minor"], "0"),
        (["--field", "patch"], "0"),
        (["--field", "file-version"], "1.0.0.0"),
    ],
)
def test_cli_prints_requested_version_field(arguments: list[str], expected: str):
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(ROOT / "version.json"), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == expected
    assert result.stderr == ""
