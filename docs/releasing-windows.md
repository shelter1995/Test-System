# Test-System Windows Installer Release Runbook

## Prerequisites

- **Windows 10/11 x64** with PowerShell 7 or Windows PowerShell 5.1
- **uv** — Python package manager (install via `pip install uv` or `winget install uv`)
- **.NET 8 SDK x64** — for desktop host compilation
- **Inno Setup 6** — installer compiler (install from https://jrsoftware.org/isinfo.php)
- **node** — for JavaScript tests
- Optional: `ffmpeg` binary, `LibreOffice` installation for enhanced document processing

## Quick Build

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

This produces:
```
dist-installer\Test-System-Setup-1.0.0-x64.exe
dist-installer\Test-System-Setup-1.0.0-x64.exe.sha256
dist-installer\build-manifest.json
```

## Build Options

```powershell
# Skip tests (for local diagnostics only; never skip for release)
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -SkipTests

# Offline prerequisites (use cached WebView2 runtime)
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -OfflinePrerequisites

# With code signing
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 `
  -CertificateThumbprint "YOUR_THUMBPRINT"

# Custom Python home (if CPython is not cached)
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 `
  -PythonHome "C:\path\to\cpython-3.13.10"

# With optional tools
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 `
  -FfmpegBin "D:\tools\ffmpeg\bin" `
  -LibreOfficePath "C:\Program Files\LibreOffice\program\soffice.exe"
```

## Offline Prerequisite Cache

The WebView2 Evergreen Standalone Runtime is cached at `.cache\prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe`.

To download it once for offline builds:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\prerequisites.ps1
```

Subsequent builds with `-OfflinePrerequisites` will validate the cached file without network access.

Validation checks:
- Authenticode signature status is `Valid`
- Signer subject contains `Microsoft Corporation`
- PE architecture is x64 (AMD64)
- File version is recorded

## Version Bump Rules

1. Edit `version.json` — only `MAJOR.MINOR.PATCH` format is accepted
2. Update `CHANGELOG.md` — entries under `## Unreleased` are promoted to the new version heading after acceptance
3. Commit version bump before running the build

```powershell
git add version.json CHANGELOG.md
git commit -m "release: bump to X.Y.Z"
```

## Changelog Format

Keep entries under `## Unreleased` during development. After acceptance testing passes on clean VMs, rename to the dated version heading.

## Outputs

| File | Description |
|------|-------------|
| `Test-System-Setup-<version>-x64.exe` | Offline Windows installer |
| `Test-System-Setup-<version>-x64.exe.sha256` | SHA-256 checksum |
| `dist-installer/build-manifest.json` | Build metadata (versions, commit, signatures) |

## SHA-256 Verification

```powershell
Get-FileHash dist-installer\Test-System-Setup-1.0.0-x64.exe -Algorithm SHA256
# Compare with the .sha256 file
```

## Code Signing

When `-CertificateThumbprint` is provided:
- The desktop host EXE is signed before staging
- The final installer EXE is signed after Inno Setup compilation
- SHA-256 digest with RFC 3161 timestamping is used
- Build manifest records `codeSigned: true`

When omitted: the build manifest records `codeSigned: false` and a warning is printed.

## MinerU Compatibility Gate

MinerU 3.3.1 must be compatible with CPython 3.13.10. To verify:

```powershell
# Run the installer build with MinerU tests
.\.venv\Scripts\python.exe -m pytest tests\test_mineru_manager.py -q
```

If PyPI has no compatible dependency set, investigate and resolve before release:
1. Check `packaging/mineru-requirements.txt` for version pins
2. Verify with a clean CPython 3.13.10 + `pip install` against those pins
3. If unresolvable, document the blocker in CHANGELOG.md

## Rollback Procedure

If a release is found to have problems:
1. Move the bad installer to `dist-installer\archive\`
2. Revert `version.json` to the last known good version
3. Fix the issue in a new branch
4. Rebuild with the corrected version

## Release Checklist

- [ ] `version.json` and `CHANGELOG.md` updated
- [ ] Python, JavaScript and .NET tests pass
- [ ] CPython is exactly 3.13.10 x64
- [ ] WebView2 prerequisite signature is valid
- [ ] clean installer build succeeds
- [ ] Windows 10 x64 fresh install passes
- [ ] Windows 11 x64 fresh install passes
- [ ] custom Chinese/space program and data paths pass
- [ ] closing the window releases ports 8002 and 8003
- [ ] Save As download, cancel and overwrite pass
- [ ] upgrade preserves selected data directory and knowledge base
- [ ] uninstall defaults to retain data
- [ ] optional MinerU install/repair and sample parse pass
- [ ] installer SHA-256 recorded
