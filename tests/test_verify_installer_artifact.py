from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_verifier():
    path = ROOT / "packaging" / "verify_installer_artifact.py"
    spec = importlib.util.spec_from_file_location("verify_installer_artifact", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage_tree(base: Path, files: dict[str, str | None]) -> Path:
    """Create a synthetic stage tree from a dict of relative-path -> content.

    A value of None creates a directory instead of a file.
    """
    base.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = base / rel
        if content is None:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return base


def _make_manifest(**overrides) -> dict:
    manifest: dict = {
        "product": {"version": "1.0.0"},
        "python": {
            "version": "3.13.10",
            "machine": "AMD64",
            "bits": "64bit",
            "path": "runtime/python/python.exe",
        },
        "base_site_packages": {
            "path": "runtime/site-packages",
            "requirements_path": "packaging/requirements-portable-base.txt",
            "requirements_sha256": "a" * 64,
        },
        "desktop": {
            "host_path": "TestSystem.exe",
            "webview2_sdk_version": "1.0.4022.49",
        },
        "mineru": {
            "bundled": False,
            "data_dir_intent": "per-user-local-app-data",
        },
        "ffmpeg": {"available": False, "path": None},
        "libreoffice": {"available": False, "path": None},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(manifest.get(key), dict):
            manifest[key].update(value)
        else:
            manifest[key] = value
    return manifest


class TestArtifactAuditorRejects:
    """Tests that the auditor correctly rejects invalid staging trees."""

    def test_rejects_wrong_python_version(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest(python={"version": "3.9.7", "machine": "AMD64", "bits": "64bit", "path": "runtime/python/python.exe"})),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="Python"):
            verifier.audit_install_image(stage)

    def test_rejects_wrong_python_architecture(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest(python={"version": "3.13.10", "machine": "x86", "bits": "32bit", "path": "runtime/python/python.exe"})),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="Python"):
            verifier.audit_install_image(stage)

    def test_rejects_version_mismatch(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "version.json": json.dumps({"version": "2.0.0"}),
            "runtime/install-manifest.json": json.dumps(_make_manifest(product={"version": "1.0.0"})),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="version"):
            verifier.audit_install_image(stage)

    def test_rejects_venv_presence(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest()),
            "version.json": json.dumps({"version": "1.0.0"}),
            ".venv/pyvenv.cfg": "home = python",
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match=r"\.venv"):
            verifier.audit_install_image(stage)

    def test_rejects_env_file(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest()),
            "version.json": json.dumps({"version": "1.0.0"}),
            "rag-anything-api/.env": "SECRET_KEY=test",
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match=r"(\.env|禁止)"):
            verifier.audit_install_image(stage)

    def test_rejects_user_data(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest()),
            "version.json": json.dumps({"version": "1.0.0"}),
            "ai-tutor-system/tutor_data/sessions/session.json": json.dumps({"id": "test"}),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="(data|tutor_data|禁止)"):
            verifier.audit_install_image(stage)

    def test_rejects_missing_host_exe(self, tmp_path: Path):
        manifest = _make_manifest()
        manifest["desktop"]["host_path"] = "MissingHost.exe"
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(manifest),
            "version.json": json.dumps({"version": "1.0.0"}),
            "TestSystem.exe": "fake-exe-content",
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="MissingHost"):
            verifier.audit_install_image(stage)

    def test_rejects_missing_python_exe(self, tmp_path: Path):
        manifest = _make_manifest()
        manifest["python"]["path"] = "runtime/python/missing-python.exe"
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(manifest),
            "version.json": json.dumps({"version": "1.0.0"}),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="python"):
            verifier.audit_install_image(stage)

    def test_rejects_missing_webview2_prerequisite_record(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest()),
            "version.json": json.dumps({"version": "1.0.0"}),
        })
        # No WebView2 prerequisite file present

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="WebView2"):
            verifier.audit_install_image(stage)

    def test_rejects_malformed_sha256(self, tmp_path: Path):
        manifest = _make_manifest()
        manifest["base_site_packages"]["requirements_sha256"] = "too-short"
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(manifest),
            "version.json": json.dumps({"version": "1.0.0"}),
        })

        verifier = _load_verifier()
        with pytest.raises(verifier.AuditError, match="SHA"):
            verifier.audit_install_image(stage)


class TestArtifactAuditorAccepts:
    """Tests that the auditor passes a valid stage and produces a JSON report."""

    def test_valid_synthetic_image_passes_and_emits_report(self, tmp_path: Path):
        stage = _stage_tree(tmp_path / "stage", {
            "runtime/install-manifest.json": json.dumps(_make_manifest()),
            "version.json": json.dumps({"version": "1.0.0"}),
            "TestSystem.exe": "fake-exe",
            "runtime/python/python.exe": "fake-python",
            ".cache/prerequisites/MicrosoftEdgeWebView2RuntimeInstallerX64.exe": "fake-webview2",
            "packaging/requirements-portable-base.txt": "pinned==1.0",
            "rag-anything-api/app.py": "# rag app",
            "ai-tutor-system/tutor_backend.py": "# tutor backend",
        })

        verifier = _load_verifier()
        report_path = tmp_path / "audit-report.json"
        verifier.audit_install_image(stage, report_path=report_path)

        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["passed"] is True
        assert "audited_at" in data
