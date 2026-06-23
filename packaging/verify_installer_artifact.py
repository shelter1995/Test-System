from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_PYTHON_VERSION = "3.13.10"
EXPECTED_PYTHON_MACHINE = "AMD64"
EXPECTED_PYTHON_BITS = "64bit"
WEBVIEW2_PREFIX = "MicrosoftEdgeWebView2RuntimeInstaller"
WEBVIEW2_MIN_SIZE = 50 * 1024 * 1024  # 50 MB — bootstrapper is ~2 MB, standalone is ~140 MB
WEBVIEW2_EXPECTED_ARCH = "AMD64"
FORBIDDEN_TOP_LEVEL = {".venv", "__pycache__", ".git", ".pytest_cache"}
FORBIDDEN_SUBDIR = {"tutor_data", "generation_output", "sessions"}
FORBIDDEN_FILES = {".env"}
FORBIDDEN_MODEL_DIRS = {"storage", "output", "models"}
# Paths where 'models' is a legitimate package directory, not user data
ALLOWED_MODEL_PARENTS = {"site-packages", "Lib", "pip", "google", "tests"}


class AuditError(ValueError):
    """Raised when an artifact audit check fails."""


def audit_install_image(
    stage: Path,
    *,
    report_path: Path | None = None,
    webview_manifest: Path | None = None,
) -> list[str]:
    stage = stage.resolve(strict=True)
    failures: list[str] = []
    passed = False

    try:
        _check_manifest(stage, failures)
        _check_forbidden_items(stage, failures)
        _check_required_files(stage, failures, webview_manifest=webview_manifest)
        _check_version_consistency(stage, failures)
    except Exception as exc:
        failures.append(f"Audit crashed: {exc}")

    passed = len(failures) == 0
    report = {
        "passed": passed,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "stage": str(stage),
        "failures": failures,
    }
    if report_path is not None:
        report_path = report_path.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not passed:
        raise AuditError("\n".join(failures))
    return failures


def _load_manifest(stage: Path) -> dict:
    manifest_path = stage / "runtime" / "install-manifest.json"
    if not manifest_path.is_file():
        raise AuditError(f"Missing install-manifest.json: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _check_manifest(stage: Path, failures: list[str]) -> None:
    try:
        manifest = _load_manifest(stage)
    except AuditError as exc:
        failures.append(str(exc))
        return
    except (json.JSONDecodeError, OSError) as exc:
        failures.append(f"Malformed install-manifest.json: {exc}")
        return

    python = manifest.get("python", {})
    if python.get("version") != EXPECTED_PYTHON_VERSION:
        failures.append(
            f"Python version mismatch: expected {EXPECTED_PYTHON_VERSION}, "
            f"got {python.get('version')}"
        )
    if python.get("machine") != EXPECTED_PYTHON_MACHINE:
        failures.append(
            f"Python machine mismatch: expected {EXPECTED_PYTHON_MACHINE}, "
            f"got {python.get('machine')}"
        )
    if python.get("bits") != EXPECTED_PYTHON_BITS:
        failures.append(
            f"Python bits mismatch: expected {EXPECTED_PYTHON_BITS}, "
            f"got {python.get('bits')}"
        )

    reqs_sha = (
        manifest.get("base_site_packages", {}).get("requirements_sha256", "")
    )
    if not re.fullmatch(r"[0-9a-f]{64}", reqs_sha or ""):
        failures.append("Missing or malformed requirements SHA-256")


def _is_under_allowed_model_parent(relative: Path) -> bool:
    """Check if a path is under an allowed parent where 'models' is a package dir."""
    return any(
        parent.lower() in ALLOWED_MODEL_PARENTS
        for parent in relative.parts[:-1]
    )


def _check_forbidden_items(stage: Path, failures: list[str]) -> None:
    for entry in stage.iterdir():
        if entry.name.lower() in FORBIDDEN_TOP_LEVEL:
            failures.append(f"Forbidden top-level item present: {entry.name}")
        if entry.is_dir():
            for subpath in entry.rglob("*"):
                if subpath.is_file() and subpath.name == ".env":
                    failures.append(f".env file found in install image: {subpath.relative_to(stage)}")
                if subpath.is_dir() and subpath.name.lower() in FORBIDDEN_SUBDIR:
                    failures.append(f"User data directory found in install image: {subpath.relative_to(stage)}")
                if subpath.is_dir() and subpath.name.lower() in FORBIDDEN_MODEL_DIRS:
                    if not _is_under_allowed_model_parent(subpath.relative_to(stage)):
                        failures.append(f"User data directory found in install image: {subpath.relative_to(stage)}")


def _check_required_files(
    stage: Path,
    failures: list[str],
    *,
    webview_manifest: Path | None = None,
) -> None:
    manifest = _load_manifest(stage)

    host_path = manifest.get("desktop", {}).get("host_path", "TestSystem.exe")
    host_file = stage / host_path
    if not host_file.is_file():
        failures.append(f"Desktop host missing: {host_path}")

    python_path = manifest.get("python", {}).get("path", "runtime/python/python.exe")
    python_file = stage / python_path
    if not python_file.is_file():
        failures.append(f"Python executable missing: {python_path}")

    webview2_found = False
    if webview_manifest is not None and webview_manifest.is_file():
        try:
            raw = webview_manifest.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            data = json.loads(raw.decode("utf-8"))
            sha = data.get("sha256", "")
            if sha and re.fullmatch(r"[0-9a-f]{64}", sha):
                webview2_found = True
                # Validate size: must be 50MB+ (reject bootstrapper)
                size = data.get("size", 0)
                if isinstance(size, int) and size < WEBVIEW2_MIN_SIZE:
                    failures.append(
                        f"WebView2 prerequisite is a bootstrapper "
                        f"({size / 1024 / 1024:.0f} MB), "
                        f"not the offline standalone installer (min {WEBVIEW2_MIN_SIZE / 1024 / 1024:.0f} MB)"
                    )
                # Validate architecture
                arch = data.get("architecture", "")
                if arch != WEBVIEW2_EXPECTED_ARCH:
                    failures.append(
                        f"WebView2 architecture is '{arch}', expected '{WEBVIEW2_EXPECTED_ARCH}'"
                    )
                # Validate signer subject
                signer = data.get("signerSubject", "")
                if not signer or "Microsoft Corporation" not in str(signer):
                    failures.append(
                        f"WebView2 signerSubject is missing or not Microsoft Corporation: {signer}"
                    )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    if not webview2_found:
        webview2_dir = stage / ".cache" / "prerequisites"
        if webview2_dir.is_dir():
            for child in webview2_dir.iterdir():
                if child.is_file() and WEBVIEW2_PREFIX in child.name:
                    webview2_found = True
                    break
    if not webview2_found:
        failures.append("WebView2 Runtime prerequisite not found")


def _check_version_consistency(stage: Path, failures: list[str]) -> None:
    version_file = stage / "version.json"
    manifest = _load_manifest(stage)
    manifest_version = manifest.get("product", {}).get("version", "")

    if version_file.is_file():
        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            file_version = data.get("version", "")
        except (json.JSONDecodeError, OSError) as exc:
            failures.append(f"Unable to read version.json: {exc}")
            return
        if file_version != manifest_version:
            failures.append(
                f"Version mismatch: version.json={file_version}, "
                f"manifest={manifest_version}"
            )

    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest_version):
        failures.append(f"Invalid product version in manifest: {manifest_version}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Test-System install image.")
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--version-file", type=Path)
    parser.add_argument("--webview-manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        audit_install_image(
            args.stage,
            report_path=args.report,
            webview_manifest=args.webview_manifest,
        )
    except AuditError as exc:
        parser.exit(2, str(exc) + "\n")
    print("Audit passed.")


if __name__ == "__main__":
    main()
