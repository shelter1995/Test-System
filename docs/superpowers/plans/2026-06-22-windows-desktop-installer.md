# Test-System Windows Desktop Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable Windows 10/11 x64 release pipeline that produces one offline `Test-System-Setup-<version>-x64.exe`, launches the existing web application inside WebView2, keeps Python services hidden and bound to the desktop window lifecycle, preserves user data across upgrades, and optionally installs MinerU plus Pipeline models over the network.

**Architecture:** Keep the existing Python services and source-development workflow intact. Add environment-variable-based data path overrides, authenticated localhost shutdown endpoints, a self-contained .NET 8 WinForms host that owns both Python processes through a Windows Job Object, and an Inno Setup installer with selectable program/data directories. Reuse and harden the existing CPython 3.13.10 portable builder; package the WebView2 Evergreen Standalone Runtime inside the final installer and keep MinerU in a separate data-directory dependency layer.

**Tech Stack:** CPython 3.13.10 x64, pytest, FastAPI/Uvicorn, .NET 8 WinForms x64, Microsoft.Web.WebView2 1.0.4022.49, xUnit, Inno Setup 6, PowerShell 7/Windows PowerShell 5.1.

**Approved design:** `docs/superpowers/specs/2026-06-22-windows-desktop-installer-design.md`

---

## 0. Execution rules and file map

The implementing agent must obey these rules throughout:

- Use TDD for Python and .NET behavior: add one failing test, run it and capture the expected failure, implement the smallest change, then rerun targeted and regression tests.
- Do not copy `.venv`, real `.env`, knowledge bases, sessions, generated files, logs, or model caches into staging.
- Do not alter source-mode defaults. With no `TEST_SYSTEM_*` variables, existing paths and `start_services.bat` behavior must remain unchanged.
- Do not kill unknown processes that happen to own ports 8002/8003.
- Do not commit downloaded runtimes, NuGet caches, installer EXEs, generated staging folders, or final installers.
- Commit after each numbered task using the exact commit intent shown; if a task requires a small corrective commit, keep it scoped to that task.
- Run all commands from repository root `D:\GitHub_WorkSpace\Test-System` unless a step specifies another directory.

Final file ownership:

```text
version.json                                      product version source
ai-tutor-system/runtime_paths.py                  tutor data/output path policy
ai-tutor-system/runtime_control.py                authenticated shutdown route
rag-anything-api/runtime_paths.py                 RAG data/output path policy
rag-anything-api/runtime_control.py               authenticated shutdown route
packaging/product_version.py                      version parsing/generation
packaging/mineru_manager.py                       optional dependency/model installer
packaging/installer_builder.py                    clean install-image staging
packaging/prerequisites.ps1                       official WebView2 prerequisite fetch/validation
packaging/build_installer.ps1                     end-to-end release build
packaging/verify_installer_artifact.py             staging/final artifact audit
desktop-host/TestSystem.Desktop.sln               .NET solution
desktop-host/src/TestSystem.Desktop/*             WinForms application
desktop-host/tests/TestSystem.Desktop.Tests/*     xUnit tests
installer/TestSystem.iss                          Inno Setup definition
installer/includes/version.iss                    generated, ignored
tests/*                                           packaging/version/runtime tests
docs/releasing-windows.md                         maintainer release runbook
```

## Task 1: Establish product version and ignored build boundaries

**Files:**

- Create: `version.json`
- Create: `packaging/product_version.py`
- Create: `tests/test_product_version.py`
- Modify: `.gitignore`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write failing version contract tests**

Create `tests/test_product_version.py`:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "packaging" / "product_version.py"
    spec = importlib.util.spec_from_file_location("product_version", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_file_is_valid_semver_and_initially_1_0_0():
    data = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    assert data == {"version": "1.0.0"}


def test_read_product_version_exposes_numeric_components(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "version.json"
    source.write_text('{"version":"2.3.4"}', encoding="utf-8")
    version = module.read_product_version(source)
    assert version.text == "2.3.4"
    assert version.file_version == "2.3.4.0"
    assert (version.major, version.minor, version.patch) == (2, 3, 4)


def test_read_product_version_rejects_prerelease_and_extra_keys(tmp_path: Path):
    module = _load_module()
    for payload in ({"version": "1.0.0-beta"}, {"version": "1.0.0", "other": 1}):
        source = tmp_path / "version.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        try:
            module.read_product_version(source)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid payload: {payload}")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_product_version.py -q
```

Expected: FAIL because `version.json` and `packaging/product_version.py` do not exist.

- [ ] **Step 3: Implement the minimal version parser**

Create `version.json`:

```json
{
  "version": "1.0.0"
}
```

Create `packaging/product_version.py` with immutable `ProductVersion`, strict `^\d+\.\d+\.\d+$` parsing, rejection of keys other than `version`, and a CLI that prints the version by default or `major`, `minor`, `patch`, `file-version` with `--field`.

Required public API:

```python
@dataclass(frozen=True)
class ProductVersion:
    text: str
    major: int
    minor: int
    patch: int

    @property
    def file_version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}.0"


def read_product_version(path: str | Path) -> ProductVersion:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version"}:
        raise ValueError("version.json must contain only the version key")
    text = payload["version"]
    if not isinstance(text, str) or re.fullmatch(r"\d+\.\d+\.\d+", text) is None:
        raise ValueError("version must use MAJOR.MINOR.PATCH")
    major, minor, patch = (int(item) for item in text.split("."))
    return ProductVersion(text=text, major=major, minor=minor, patch=patch)
```

Add these patterns to `.gitignore`:

```gitignore
dist-installer/
.build/
.cache/prerequisites/
desktop-host/**/bin/
desktop-host/**/obj/
installer/includes/version.iss
```

Add an `Unreleased` section to `CHANGELOG.md` recording the planned Windows installer work without claiming it is shipped.

- [ ] **Step 4: Verify GREEN and parser CLI**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_product_version.py -q
.\.venv\Scripts\python.exe packaging\product_version.py version.json --field file-version
git diff --check
```

Expected: tests PASS; CLI prints `1.0.0.0`; diff check has no errors.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore CHANGELOG.md version.json packaging/product_version.py tests/test_product_version.py
git commit -m "build: establish product version contract"
```

## Task 2: Make all mutable Python paths data-root aware

**Files:**

- Create: `ai-tutor-system/runtime_paths.py`
- Create: `rag-anything-api/runtime_paths.py`
- Create: `ai-tutor-system/tests/test_runtime_paths.py`
- Modify: `ai-tutor-system/tutor_config.py`
- Modify: `ai-tutor-system/generation_runner.py`
- Modify: `ai-tutor-system/generation_api.py`
- Modify: `ai-tutor-system/tests/test_generation_api.py`
- Modify: `rag-anything-api/config.py`
- Modify: `rag-anything-api/tests/test_config_runtime_paths.py`

- [ ] **Step 1: Add failing RAG path tests**

Extend `rag-anything-api/tests/test_config_runtime_paths.py` using the file's existing fresh-import helper. Assert that with:

```python
monkeypatch.setenv("TEST_SYSTEM_RAG_STORAGE_DIR", str(tmp_path / "rag" / "storage"))
monkeypatch.setenv("TEST_SYSTEM_RAG_OUTPUT_DIR", str(tmp_path / "rag" / "output"))
```

a fresh `config.py` import produces:

```python
assert config.STORAGE_ROOT == (tmp_path / "rag" / "storage").resolve()
assert config.RAGANYTHING_OUTPUT_ROOT == (tmp_path / "rag" / "output").resolve()
assert config.DATABASE_REGISTRY_FILE == config.STORAGE_ROOT / "databases.json"
assert config.TRADITIONAL_RAG_STORAGE_ROOT == config.STORAGE_ROOT / "traditional_rag"
```

Add a second test proving absent variables retain `rag-anything-api/storage` and `rag-anything-api/output`.
Add an environment-file test: with `TEST_SYSTEM_DATA_DIR=<tmp>`, a fresh import loads `<tmp>/config/rag.env`; without it, the service continues loading `rag-anything-api/.env`. The test must place a harmless sentinel setting in each file and assert the data-directory file wins only in installed mode.

- [ ] **Step 2: Run RAG test and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_config_runtime_paths.py -q
```

Expected: new override assertions FAIL because paths still derive from `BASE_DIR`.

- [ ] **Step 3: Implement RAG runtime paths**

Create `rag-anything-api/runtime_paths.py`:

```python
from __future__ import annotations

import os
from pathlib import Path


def absolute_env_path(name: str, fallback: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback.resolve()
    value = Path(raw).expanduser()
    if not value.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return value.resolve()
```

In `rag-anything-api/config.py`, select the environment file before reading settings: installed mode uses `Path(TEST_SYSTEM_DATA_DIR) / "config" / "rag.env"`; source mode uses the current `.env`. Then replace fixed path roots with:

```python
from runtime_paths import absolute_env_path

BASE_DIR = Path(__file__).resolve().parent
STORAGE_ROOT = absolute_env_path("TEST_SYSTEM_RAG_STORAGE_DIR", BASE_DIR / "storage")
RAGANYTHING_OUTPUT_ROOT = absolute_env_path("TEST_SYSTEM_RAG_OUTPUT_DIR", BASE_DIR / "output")
```

Keep all existing child paths derived from those roots. Set installed-host defaults in the desktop process environment, not in Python source.

- [ ] **Step 4: Verify RAG GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_config_runtime_paths.py -q
```

Expected: PASS.

- [ ] **Step 5: Add failing tutor path and artifact security tests**

Create `ai-tutor-system/tests/test_runtime_paths.py` to fresh-import `runtime_paths.py` and assert:

```python
paths = module.resolve_runtime_paths(
    {
        "TEST_SYSTEM_TUTOR_DATA_DIR": str(tmp_path / "tutor_data"),
        "TEST_SYSTEM_GENERATION_OUTPUT_DIR": str(tmp_path / "generated"),
        "TEST_SYSTEM_LOG_DIR": str(tmp_path / "logs"),
    },
    source_root=tmp_path / "source",
)
assert paths.tutor_data == (tmp_path / "tutor_data").resolve()
assert paths.generation_output == (tmp_path / "generated").resolve()
assert paths.logs == (tmp_path / "logs").resolve()
```

Add tests for fallback paths and rejection of relative overrides. Extend `ai-tutor-system/tests/test_generation_api.py` so `_resolve_artifact_path("generation_output/report.md")` resolves under an injected external artifact root, while `../secret` and paths outside that root still raise 400/403.
Add the matching tutor environment-file test: installed mode loads `<DataDir>/config/tutor.env`; source mode still loads `ai-tutor-system/.env`. Existing OS environment values must retain `python-dotenv`'s non-overriding behavior.

- [ ] **Step 6: Run tutor tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests\test_runtime_paths.py ai-tutor-system\tests\test_generation_api.py -q
```

Expected: FAIL because `runtime_paths.py` and external artifact-root injection do not exist.

- [ ] **Step 7: Implement tutor path policy**

Create `ai-tutor-system/runtime_paths.py` with:

```python
@dataclass(frozen=True)
class RuntimePaths:
    tutor_data: Path
    generation_output: Path
    logs: Path


def resolve_runtime_paths(
    environ: Mapping[str, str] | None = None,
    *,
    source_root: Path | None = None,
) -> RuntimePaths:
    env = os.environ if environ is None else environ
    root = (source_root or Path(__file__).resolve().parent.parent).resolve()

    def resolve(name: str, fallback: Path) -> Path:
        raw = str(env.get(name, "")).strip()
        if not raw:
            return fallback.resolve()
        value = Path(raw).expanduser()
        if not value.is_absolute():
            raise ValueError(f"{name} must be an absolute path")
        return value.resolve()

    return RuntimePaths(
        tutor_data=resolve(
            "TEST_SYSTEM_TUTOR_DATA_DIR",
            root / "ai-tutor-system" / "tutor_data",
        ),
        generation_output=resolve(
            "TEST_SYSTEM_GENERATION_OUTPUT_DIR",
            root / "generation_output",
        ),
        logs=resolve("TEST_SYSTEM_LOG_DIR", root / "runtime" / "logs"),
    )


def get_runtime_paths() -> RuntimePaths:
    return resolve_runtime_paths()
```

Use absolute-path validation identical to the RAG helper. `source_root` defaults to the repository root (`Path(__file__).resolve().parent.parent`), preserving current `generation_output`; tutor data fallback remains `ai-tutor-system/tutor_data`.

Update `tutor_config.py` to select `<DataDir>/config/tutor.env` when `TEST_SYSTEM_DATA_DIR` exists, otherwise the source `.env`, then derive `DATA_DIR`, sessions, history and scenarios from `get_runtime_paths().tutor_data`. Update `generation_runner.py` to derive `JOBS_DIR` from tutor data and `OUTPUT_DIR` from `generation_output`. Update `generation_api.py`:

```python
def _resolve_artifact_path(path: str, artifact_root: Path | None = None) -> Path:
    root = (artifact_root or get_runtime_paths().generation_output).resolve()
    parts = Path(path).parts
    relative = Path(*parts[1:]) if parts and parts[0] == "generation_output" else Path(path)
    if ".." in relative.parts or relative.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return resolved
```

Preserve the API's external `generation_output/<filename>` path format so existing frontend and stored job records do not change.

- [ ] **Step 8: Verify tutor GREEN and path regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests\test_runtime_paths.py ai-tutor-system\tests\test_generation_api.py ai-tutor-system\tests\test_generation_runner.py -q
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_config_runtime_paths.py rag-anything-api\tests\test_database_registry.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add ai-tutor-system/runtime_paths.py ai-tutor-system/tutor_config.py ai-tutor-system/generation_runner.py ai-tutor-system/generation_api.py ai-tutor-system/tests/test_runtime_paths.py ai-tutor-system/tests/test_generation_api.py rag-anything-api/runtime_paths.py rag-anything-api/config.py rag-anything-api/tests/test_config_runtime_paths.py
git commit -m "feat: separate runtime data from program files"
```

## Task 3: Add authenticated graceful shutdown to both services

**Files:**

- Create: `ai-tutor-system/runtime_control.py`
- Create: `rag-anything-api/runtime_control.py`
- Create: `ai-tutor-system/tests/test_runtime_control.py`
- Create: `rag-anything-api/tests/test_runtime_control.py`
- Modify: `ai-tutor-system/tutor_backend.py`
- Modify: `rag-anything-api/app.py`
- Modify: `rag-anything-api/start.py`

- [ ] **Step 1: Write failing route tests for both services**

In each service test module, build a minimal FastAPI app, call `install_shutdown_route(app, token="secret")`, assign a fake server with `should_exit = False`, and assert:

```python
assert client.post("/__desktop/shutdown").status_code == 403
assert client.post(
    "/__desktop/shutdown",
    headers={"X-Test-System-Shutdown-Token": "wrong"},
).status_code == 403
response = client.post(
    "/__desktop/shutdown",
    headers={"X-Test-System-Shutdown-Token": "secret"},
)
assert response.json() == {"status": "shutting_down"}
assert fake_server.should_exit is True
```

Also assert no configured token returns 404, and a request whose client host is not `127.0.0.1` or `::1` returns 403.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests\test_runtime_control.py rag-anything-api\tests\test_runtime_control.py -q
```

Expected: FAIL because runtime control modules do not exist.

- [ ] **Step 3: Implement the route in each service**

Use the same small implementation in each service-local module so neither source launcher needs repository-root import changes:

```python
def install_shutdown_route(app: FastAPI, token: str | None = None) -> None:
    expected = token if token is not None else os.getenv("TEST_SYSTEM_SHUTDOWN_TOKEN", "")

    @app.post("/__desktop/shutdown", include_in_schema=False)
    async def desktop_shutdown(request: Request, x_test_system_shutdown_token: str = Header(default="")):
        if not expected:
            raise HTTPException(status_code=404)
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(status_code=403)
        if not hmac.compare_digest(expected, x_test_system_shutdown_token):
            raise HTTPException(status_code=403)
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is None:
            raise HTTPException(status_code=503, detail="Server control unavailable")
        server.should_exit = True
        return {"status": "shutting_down"}
```

Allow `testclient` only when the module is running under tests by injecting an allowed-host set into `install_shutdown_route`; do not hard-code it in production defaults.

- [ ] **Step 4: Wire Uvicorn server instances**

In `rag-anything-api/start.py`, replace the existing `uvicorn.run` call with:

```python
server = uvicorn.Server(uvicorn.Config(
    "app:app",
    host=config.RAG_SERVICE_HOST,
    port=config.RAG_SERVICE_PORT,
    log_level="info",
    reload=False,
))
from app import app
app.state.uvicorn_server = server
server.run()
```

Install the shutdown route once when each FastAPI app is created. Make the equivalent `uvicorn.Server` change in `tutor_backend.py`'s `__main__` block. Force desktop-host service bindings to loopback using process environment values `RAG_SERVICE_HOST=127.0.0.1` and `TUTOR_SERVICE_HOST=127.0.0.1`; keep source defaults untouched for compatibility.

- [ ] **Step 5: Verify GREEN and app regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest ai-tutor-system\tests\test_runtime_control.py ai-tutor-system\tests\test_tutor_backend.py rag-anything-api\tests\test_runtime_control.py rag-anything-api\tests\test_app_lifespan.py rag-anything-api\tests\test_api_contract.py -q
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api
```

Expected: PASS with no compile errors.

- [ ] **Step 6: Commit**

```powershell
git add ai-tutor-system/runtime_control.py ai-tutor-system/tutor_backend.py ai-tutor-system/tests/test_runtime_control.py rag-anything-api/runtime_control.py rag-anything-api/app.py rag-anything-api/start.py rag-anything-api/tests/test_runtime_control.py
git commit -m "feat: support authenticated desktop shutdown"
```

## Task 4: Create an install-image builder with strict Python x64 validation

**Files:**

- Create: `packaging/installer_builder.py`
- Create: `tests/test_installer_builder.py`
- Modify: `packaging/portable_builder.py`
- Modify: `tests/test_portable_builder.py`
- Modify: `packaging/requirements-portable-base.txt`

- [ ] **Step 1: Add failing architecture and clean-stage tests**

Extend `tests/test_portable_builder.py` so `validate_python_runtime` runs:

```python
import json, platform
print(json.dumps({"version": platform.python_version(), "machine": platform.machine(), "bits": platform.architecture()[0]}))
```

and rejects any result other than `3.13.10`, `AMD64`, `64bit`.

Create `tests/test_installer_builder.py` to assert:

- staging is named `Test-System` rather than `Test-System-Portable`;
- staging includes only runtime application files, `version.json`, and published desktop host files;
- staging excludes `.venv`, `.env`, data directories, `docs/superpowers`, tests, caches and build output;
- generated `runtime/install-manifest.json` uses only relative paths and includes product version, Python version/arch, WebView2 SDK version and dependency file SHA-256;
- optional site-packages and models are not created under the program image.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_portable_builder.py tests\test_installer_builder.py -q
```

Expected: FAIL on architecture validation and missing installer builder.

- [ ] **Step 3: Harden shared Python validation**

Change `validate_python_runtime` to parse one JSON response and return a typed dictionary. Preserve portable builder callers by updating their manifest call. Reject mismatches with a message containing expected and actual version, machine and bits.

Use `uv pip compile` in a later release-maintenance step, but keep `packaging/requirements-portable-base.txt` fully pinned and include a comment that Python 3.13.10 is the lock target. Do not add MinerU to this file.

- [ ] **Step 4: Implement `installer_builder.py`**

Required CLI:

```powershell
python packaging\installer_builder.py `
  --root . `
  --output-root .build\installer `
  --python-home <CPythonHome> `
  --desktop-publish desktop-host\publish `
  --version-file version.json
```

Required public function name and parameters are `build_install_image(root: Path, output_root: Path, python_home: Path, desktop_publish: Path, *, ffmpeg_bin: str | None = None, libreoffice_path: str | None = None) -> Path`.

Reuse narrow helpers from `portable_builder.py` rather than invoking one builder from the other. Copy only `ai-tutor-system`, `rag-anything-api`, selected `packaging/*.py` and requirement files, `assets`, `version.json`, license/user documentation, runtime tools, Python runtime, base dependencies, and desktop publish output. Generate `.env` from examples only for source compatibility; installed services must load data-directory config first.

- [ ] **Step 5: Verify GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_portable_builder.py tests\test_installer_builder.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packaging/installer_builder.py packaging/portable_builder.py packaging/requirements-portable-base.txt tests/test_installer_builder.py tests/test_portable_builder.py
git commit -m "build: create clean Windows install image"
```

## Task 5: Scaffold the .NET desktop host and configuration boundary

**Files:**

- Create: `desktop-host/TestSystem.Desktop.sln`
- Create: `desktop-host/Directory.Packages.props`
- Create: `desktop-host/src/TestSystem.Desktop/TestSystem.Desktop.csproj`
- Create: `desktop-host/src/TestSystem.Desktop/Program.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Configuration/InstallConfiguration.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Configuration/RuntimeLayout.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Configuration/RuntimeEnvironment.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Diagnostics/AppLog.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/TestSystem.Desktop.Tests.csproj`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/ConfigurationTests.cs`

- [ ] **Step 1: Scaffold solution and projects without application behavior**

Run:

```powershell
dotnet new sln -n TestSystem.Desktop -o desktop-host
dotnet new winforms -n TestSystem.Desktop -o desktop-host\src\TestSystem.Desktop --framework net8.0
dotnet new xunit -n TestSystem.Desktop.Tests -o desktop-host\tests\TestSystem.Desktop.Tests --framework net8.0
dotnet sln desktop-host\TestSystem.Desktop.sln add desktop-host\src\TestSystem.Desktop\TestSystem.Desktop.csproj desktop-host\tests\TestSystem.Desktop.Tests\TestSystem.Desktop.Tests.csproj
dotnet add desktop-host\tests\TestSystem.Desktop.Tests\TestSystem.Desktop.Tests.csproj reference desktop-host\src\TestSystem.Desktop\TestSystem.Desktop.csproj
```

Set both projects to `net8.0-windows`, x64, nullable enabled and implicit usings enabled. Set app `AssemblyName=TestSystem`, `OutputType=WinExe`, `UseWindowsForms=true`, `RuntimeIdentifier=win-x64`, `SelfContained=true`, `PublishSingleFile=false`, and `ApplicationIcon` to the existing `assets/test-system.ico` through a linked project item. Add central package versions:

```xml
<Project>
  <PropertyGroup><ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally></PropertyGroup>
  <ItemGroup>
    <PackageVersion Include="Microsoft.Web.WebView2" Version="1.0.4022.49" />
    <PackageVersion Include="Microsoft.NET.Test.Sdk" Version="17.14.1" />
    <PackageVersion Include="xunit" Version="2.9.3" />
    <PackageVersion Include="xunit.runner.visualstudio" Version="3.1.5" />
  </ItemGroup>
</Project>
```

Reference WebView2 from the app project and test packages from the test project. Delete template `Form1.*` and `UnitTest1.cs`.

- [ ] **Step 2: Write failing configuration tests**

Test these cases with temporary directories:

- valid `{ "dataDir": "C:\\Data\\Test-System", "installId": "d1cf6b3d-77b3-4bfc-a2b1-be0a8a7cb35d" }` parses to an absolute path;
- missing file, relative path, empty `dataDir`, malformed JSON and missing install ID are rejected with Chinese user-facing messages;
- `RuntimeLayout` derives Python, service roots, logs, WebView2 user data, optional packages and model directories exactly from install/data roots;
- `RuntimeEnvironment.Build()` sets loopback hosts, ports, shutdown token, all `TEST_SYSTEM_*` paths, local Python/site-packages/tool paths, model caches and UTF-8 without mutating `Environment` globally.

- [ ] **Step 3: Run tests and verify RED**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --no-restore
```

Expected: FAIL because configuration classes do not exist. If restore is required, run `dotnet restore desktop-host\TestSystem.Desktop.sln --locked-mode` after committing `packages.lock.json`; do not accept floating restore output.

- [ ] **Step 4: Implement configuration, layout and rolling log**

Use this external contract:

```csharp
public sealed record InstallConfiguration(string DataDir, Guid InstallId)
{
    public static InstallConfiguration Load(string installRoot);
}

public sealed record RuntimeLayout(
    string InstallRoot,
    string DataRoot,
    string PythonExe,
    string RagRoot,
    string TutorRoot,
    string LogsRoot,
    string WebViewUserData,
    string OptionalSitePackages,
    string MineruModels)
{
    public static RuntimeLayout Create(string installRoot, string dataRoot);
    public void EnsureWritableDirectories();
}

public static class RuntimeEnvironment
{
    public static IReadOnlyDictionary<string, string> Build(RuntimeLayout layout, string shutdownToken);
}
```

`InstallConfiguration.Load` reads `<InstallRoot>\install-location.json`. `EnsureWritableDirectories` performs a create/write/rename/delete probe. `AppLog` writes UTF-8 to `<DataDir>\logs\desktop-host.log`, rotates at 5 MiB and retains five numbered files; logging failures must not crash startup.

On first start, `RuntimeLayout.EnsureWritableDirectories` also creates `<DataDir>\config`. If `rag.env` or `tutor.env` is absent, copy the corresponding installed `.env.example` using create-new semantics; never overwrite an existing data-directory environment file during startup or upgrade.

- [ ] **Step 5: Verify GREEN and publish smoke test**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release
dotnet publish desktop-host\src\TestSystem.Desktop\TestSystem.Desktop.csproj -c Release -r win-x64 --self-contained true -o .build\desktop-smoke
Test-Path .build\desktop-smoke\TestSystem.exe
```

Expected: tests PASS and final command prints `True`.

- [ ] **Step 6: Commit**

```powershell
git add desktop-host
git commit -m "feat: scaffold Windows desktop host"
```

## Task 6: Implement owned backend process lifecycle and Job Object cleanup

**Files:**

- Create: `desktop-host/src/TestSystem.Desktop/Processes/IBackendProcess.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Processes/BackendProcess.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Processes/WindowsJobObject.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Processes/BackendProcessSupervisor.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Processes/PortOwnershipGuard.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/ProcessSupervisorTests.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/JobObjectIntegrationTests.cs`

- [ ] **Step 1: Write failing process-supervisor tests**

Tests must use real short-lived child processes where practical. Cover:

- Python commands use the bundled executable and service working directory;
- `UseShellExecute=false`, `CreateNoWindow=true`, stdout/stderr redirected;
- environment is replaced with the explicit runtime dictionary;
- exit before readiness exposes exit code and the correct log path;
- shutdown POST is sent to each owned healthy service with `X-Test-System-Shutdown-Token`;
- after a 10-second configurable test clock timeout, remaining owned process trees are killed;
- an unowned listener on 8002 or 8003 causes startup rejection and is still alive afterward;
- disposing a real Job Object terminates a spawned long-running test child.

Use injectable ports and sub-second timeouts in tests; production constants remain 8002, 8003 and 10 seconds.

- [ ] **Step 2: Run tests and verify RED**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~ProcessSupervisor|FullyQualifiedName~JobObject"
```

Expected: FAIL because process classes do not exist.

- [ ] **Step 3: Implement Job Object and process wrapper**

`WindowsJobObject` must P/Invoke `CreateJobObject`, `SetInformationJobObject` with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`, and `CloseHandle`. Throw a `Win32Exception` with the native error when setup or assignment fails. Keep one Job Object for the host lifetime.

`BackendProcess` wraps `System.Diagnostics.Process`, asynchronously drains stdout/stderr into service log files, exposes PID/exit, and never opens a console. Start each process and immediately assign it to the Job Object before waiting for health.

- [ ] **Step 4: Implement port guard and supervisor**

Before starting either service, bind a temporary `TcpListener` to its loopback endpoint and immediately release it. Failure means the port is occupied; abort with a Chinese message and do not inspect or kill the owner.

Use these commands:

```text
RAG:   <PythonExe> start.py       working directory <InstallRoot>\rag-anything-api
Tutor: <PythonExe> tutor_backend.py working directory <InstallRoot>\ai-tutor-system
```

`BackendProcessSupervisor.StopAsync()` posts to both shutdown endpoints concurrently, waits at most 10 seconds total, then calls `Kill(entireProcessTree: true)` for remaining direct children and disposes the Job Object.

- [ ] **Step 5: Verify GREEN repeatedly**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~ProcessSupervisor|FullyQualifiedName~JobObject"
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~JobObjectIntegrationTests" -- RunConfiguration.MaxCpuCount=1
```

Expected: PASS on three consecutive runs; no test child remains in Task Manager or `Get-Process` output.

- [ ] **Step 6: Commit**

```powershell
git add desktop-host/src/TestSystem.Desktop/Processes desktop-host/tests/TestSystem.Desktop.Tests/ProcessSupervisorTests.cs desktop-host/tests/TestSystem.Desktop.Tests/JobObjectIntegrationTests.cs
git commit -m "feat: bind backend processes to desktop lifetime"
```

## Task 7: Add startup coordination and single-instance activation

**Files:**

- Create: `desktop-host/src/TestSystem.Desktop/Startup/IHealthProbe.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Startup/HttpHealthProbe.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Startup/StartupCoordinator.cs`
- Create: `desktop-host/src/TestSystem.Desktop/SingleInstance/SingleInstanceCoordinator.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/StartupCoordinatorTests.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/SingleInstanceTests.cs`

- [ ] **Step 1: Write failing coordinator tests**

Assert the exact order:

1. validate layout;
2. guard both ports;
3. start RAG;
4. wait for `http://127.0.0.1:8003/health`;
5. start Tutor;
6. wait for `http://127.0.0.1:8002/api/status`;
7. return ready.

Cover health HTTP 200, transient connection errors, non-success responses, child exit, cancellation and 120-second total timeout. Verify any failure calls supervisor stop exactly once and returns an error model containing summary, detail and log directory.

For single instance, use a unique per-test app ID; assert first instance owns the mutex, second instance sends an activation message and exits, and first receives activation. Use named pipes for activation and a per-user mutex name containing the current Windows SID plus stable product GUID.

- [ ] **Step 2: Run tests and verify RED**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~StartupCoordinator|FullyQualifiedName~SingleInstance"
```

Expected: FAIL because classes do not exist.

- [ ] **Step 3: Implement health/startup coordination**

`HttpHealthProbe` uses one `HttpClient` with a 2-second per-request timeout, one-second polling delay, cancellation, and no proxy for loopback requests. `StartupCoordinator` uses a 120-second linked cancellation source and reports startup phase changes through `IProgress<StartupPhase>`.

- [ ] **Step 4: Implement single-instance activation**

Create a named mutex and named-pipe server. The second instance writes one `activate` line then exits with code 0. The first raises an event on the UI synchronization context; the form restores from minimized state, calls `Activate()` and `BringToFront()`.

- [ ] **Step 5: Verify GREEN**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~StartupCoordinator|FullyQualifiedName~SingleInstance"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add desktop-host/src/TestSystem.Desktop/Startup desktop-host/src/TestSystem.Desktop/SingleInstance desktop-host/tests/TestSystem.Desktop.Tests/StartupCoordinatorTests.cs desktop-host/tests/TestSystem.Desktop.Tests/SingleInstanceTests.cs
git commit -m "feat: coordinate startup and single instance"
```

## Task 8: Implement the WebView2 shell, safe navigation and downloads

**Files:**

- Create: `desktop-host/src/TestSystem.Desktop/MainForm.cs`
- Create: `desktop-host/src/TestSystem.Desktop/MainForm.Designer.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Web/NavigationPolicy.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Web/DownloadCoordinator.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Web/IFileSaveDialog.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Web/WindowsFileSaveDialog.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/NavigationPolicyTests.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/DownloadCoordinatorTests.cs`
- Modify: `desktop-host/src/TestSystem.Desktop/Program.cs`
- Modify: `ai-tutor-system/static/js/generation.js`
- Modify: `ai-tutor-system/static/js/overview.js`
- Modify: `ai-tutor-system/tests/test_frontend_history_actions.js`

- [ ] **Step 1: Write failing navigation and filename tests**

Assert:

- `http://127.0.0.1:8002/workspace` is internal;
- `localhost`, port changes, credentials in URL, non-HTTP schemes and external hosts are not internal;
- `https` external links are opened by the system browser;
- dangerous `file:`, `javascript:`, `data:` and custom schemes are blocked;
- suggested download names remove `<>:"/\\|?*`, trim trailing dots/spaces, reject `CON`, `NUL`, `COM1` etc., and fall back to `download`;
- canceling the save dialog cancels the WebView2 operation;
- accepting sets a full result path without loading file content into host memory.

- [ ] **Step 2: Run tests and verify RED**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~NavigationPolicy|FullyQualifiedName~DownloadCoordinator"
```

Expected: FAIL because classes do not exist.

- [ ] **Step 3: Implement MainForm startup and error states**

Main form contains a status panel and WebView2 control. On `Shown`, run `StartupCoordinator`; only after both services are ready call:

```csharp
var environment = await CoreWebView2Environment.CreateAsync(
    browserExecutableFolder: null,
    userDataFolder: layout.WebViewUserData);
await webView.EnsureCoreWebView2Async(environment);
webView.CoreWebView2.Navigate("http://127.0.0.1:8002/");
```

Disable dev tools, browser accelerator keys and status bar in release builds. Keep the context menu only if it contains user actions without developer tools. Failure panel exposes `重试`, `打开日志目录`, `退出`.

- [ ] **Step 4: Implement navigation and downloads**

Cancel disallowed main-frame navigation. Open allowed external `http/https` links with `ProcessStartInfo.UseShellExecute=true`. Handle `DownloadStarting` with a deferral and `SaveFileDialog` configured with `OverwritePrompt=true`, initial directory `KnownFolders.Downloads`, sanitized suggested name and `Handled=true`. On cancel set `args.Cancel=true`; on accept set `args.ResultFilePath` and observe download state for completion/failure notification.

Change generated-file anchors in `generation.js` and `overview.js` to remove `target="_blank"`; keep `href` and download behavior. Extend the existing JS source tests to reject `target="_blank"` on artifact download links.

- [ ] **Step 5: Wire close lifecycle**

On `FormClosing`, cancel the first close, disable the UI, await `BackendProcessSupervisor.StopAsync()` once, dispose WebView2 and single-instance resources, then close for real. A 15-second UI-level hard cap must dispose the Job Object and exit; the supervisor's internal graceful timeout remains 10 seconds.

- [ ] **Step 6: Verify GREEN**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release
node ai-tutor-system\tests\test_frontend_history_actions.js
```

Expected: PASS.

- [ ] **Step 7: Manual source-host smoke test**

Create a temporary `install-location.json` next to the published host pointing at a temporary writable data directory, and stage the app with `installer_builder.py`. Start the host and verify: no console windows, local page renders, external link opens default browser, generated artifact shows Save As, cancel leaves no file, closing releases ports 8002/8003.

- [ ] **Step 8: Commit**

```powershell
git add desktop-host/src/TestSystem.Desktop/MainForm.cs desktop-host/src/TestSystem.Desktop/MainForm.Designer.cs desktop-host/src/TestSystem.Desktop/Program.cs desktop-host/src/TestSystem.Desktop/Web desktop-host/tests/TestSystem.Desktop.Tests/NavigationPolicyTests.cs desktop-host/tests/TestSystem.Desktop.Tests/DownloadCoordinatorTests.cs ai-tutor-system/static/js/generation.js ai-tutor-system/static/js/overview.js ai-tutor-system/tests/test_frontend_history_actions.js
git commit -m "feat: host frontend in WebView2 with safe downloads"
```

## Task 9: Build the optional MinerU package/model manager

**Files:**

- Create: `packaging/mineru_manager.py`
- Create: `tests/test_mineru_manager.py`
- Modify: `packaging/mineru-requirements.txt`
- Modify: `desktop-host/src/TestSystem.Desktop/Mineru/MineruInstallerForm.cs`
- Create: `desktop-host/src/TestSystem.Desktop/Mineru/MineruInstallerRunner.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/MineruInstallerRunnerTests.cs`
- Modify: `desktop-host/src/TestSystem.Desktop/Program.cs`

- [ ] **Step 1: Write failing Python manager tests**

Cover:

- install command uses current bundled Python, `--target <DataDir>\runtime\optional-site-packages.installing`, pinned requirements and no `--upgrade` of base dependencies;
- model command is:

```text
<PythonExe> -m mineru.cli.models_download --source modelscope --model_type pipeline
```

- environment places temporary optional packages first in `PYTHONPATH`, sets all model caches under data root and never changes install-root site-packages;
- successful verification requires distribution version `3.3.1`, `mineru.cli.client.main`, model downloader help and at least one non-config model file;
- failed pip/verify/model stages leave current working optional packages intact, remove `.installing`, retain model cache and write a structured status JSON;
- success atomically rotates current target to `.previous`, promotes `.installing`, then deletes backup;
- lock file prevents concurrent installs.

- [ ] **Step 2: Run Python tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mineru_manager.py -q
```

Expected: FAIL because manager does not exist.

- [ ] **Step 3: Implement manager CLI**

Required CLI:

```powershell
runtime\python\python.exe packaging\mineru_manager.py install `
  --package-root <InstallDir> `
  --data-root <DataDir> `
  --source modelscope `
  --status-json <DataDir>\runtime\mineru-status.json
```

Print newline-delimited JSON progress records such as:

```json
{"stage":"dependencies","percent":10,"message":"正在安装 MinerU 依赖"}
{"stage":"models","percent":60,"message":"正在下载 Pipeline 模型"}
{"stage":"complete","percent":100,"message":"增强解析组件安装完成"}
```

Pin `mineru[core]==3.3.1` and every directly declared compatibility constraint in `mineru-requirements.txt`. Installation must use the package's bundled `pip`, target-only install, temporary directory and isolated verification subprocess.

- [ ] **Step 4: Verify Python GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mineru_manager.py tests\test_portable_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing .NET runner tests**

Assert `--install-mineru` selects installer mode instead of main app mode, starts the bundled Python manager hidden, parses JSON progress, supports cancel by terminating only the manager process tree, displays log path on failure, and refuses to modify packages while the main app mutex is owned.

- [ ] **Step 6: Implement graphical installer mode**

`TestSystem.exe --install-mineru` loads installation config, shows source selector (ModelScope default, Hugging Face alternative), disk/network warning, progress bar, current stage, cancel and open-log controls. On successful completion it offers to start Test-System. Add an application menu item `安装/修复增强解析组件`; if services are running, prompt for app restart before launching manager mode.

- [ ] **Step 7: Verify .NET GREEN**

```powershell
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~MineruInstallerRunner"
```

Expected: PASS.

- [ ] **Step 8: Run clean compatibility gate**

Against a clean copy of bundled CPython 3.13.10 x64 and an empty data root, run the real manager with network access. Verify package version 3.3.1, model status success and one scanned-PDF/image sample parse. If PyPI has no compatible dependency set for CPython 3.13.10, stop release work and report the exact resolver failure; do not silently change Python or MinerU versions.

- [ ] **Step 9: Commit**

```powershell
git add packaging/mineru_manager.py packaging/mineru-requirements.txt tests/test_mineru_manager.py desktop-host/src/TestSystem.Desktop/Mineru desktop-host/src/TestSystem.Desktop/Program.cs desktop-host/tests/TestSystem.Desktop.Tests/MineruInstallerRunnerTests.cs
git commit -m "feat: add optional MinerU enhancement installer"
```

## Task 10: Implement the Inno Setup installer and safe uninstall

**Files:**

- Create: `installer/TestSystem.iss`
- Create: `installer/assets/license.txt` or reuse `LICENSE` directly
- Create: `tests/test_inno_installer_contract.py`
- Create: `desktop-host/src/TestSystem.Desktop/Uninstall/DataDeletionGuard.cs`
- Create: `desktop-host/tests/TestSystem.Desktop.Tests/DataDeletionGuardTests.cs`
- Modify: `desktop-host/src/TestSystem.Desktop/Program.cs`

- [ ] **Step 1: Write failing installer contract tests**

`tests/test_inno_installer_contract.py` should parse source text and assert:

- stable AppId, `ArchitecturesAllowed=x64compatible`, `ArchitecturesInstallIn64BitMode=x64compatible`, `PrivilegesRequired=lowest`;
- default program path `{localappdata}\Programs\Test-System`;
- custom data-directory page exists and defaults to `{localappdata}\Test-System\Data`;
- desktop and start-menu shortcuts target `{app}\TestSystem.exe`, never batch files, and use `assets\test-system.ico`;
- installer runs bundled WebView2 x64 standalone installer with `/silent /install`;
- finish page offers main app and optional `--install-mineru` mode;
- upgrade checks app mutex/process and preserves recorded data directory;
- uninstall defaults to keep data and only invokes tested host delete mode after explicit confirmation.

Write `DataDeletionGuardTests` covering rejection of empty/relative paths, drive roots, user profile root, Windows, Program Files, LocalAppData root and install root; allow only the exact configured data directory after matching install ID marker.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_inno_installer_contract.py -q
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~DataDeletionGuard"
```

Expected: FAIL because installer and deletion guard do not exist.

- [ ] **Step 3: Implement safe data deletion mode**

Add `TestSystem.exe --delete-data <absolute-path> --install-id <guid>`. It loads `<DataDir>\config\install.json`, requires exact canonical path and install ID match, applies protected-root checks, deletes contents without following reparse points, then removes the root. Return non-zero and log on any mismatch. This mode must not launch services or WebView2.

- [ ] **Step 4: Implement Inno Setup script**

Use these fixed identities:

```ini
#define MyAppId "{{D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D}"
#define MyAppName "Test-System"
DefaultDirName={localappdata}\Programs\Test-System
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
```

Load generated `installer/includes/version.iss`. Create a custom folder page for data. Validate it is absolute and writable with create/write/rename/delete probe. Persist `DataDir`, `InstallId` and version in `HKCU\Software\Test-System`; write `{app}\install-location.json` and `<DataDir>\config\install.json` as UTF-8 JSON.

Install all files from `.build\installer\Test-System\*`, plus `.cache\prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe` to `{tmp}` with `deleteafterinstall`. Run it unconditionally in silent install/repair mode after files are copied; non-zero exit aborts installation with a Chinese error.

Before upgrade, detect running app and request closure; do not overwrite while `TestSystem.exe` remains running. On uninstall ask once whether to delete the displayed data directory; default answer is No. If Yes, execute the tested delete mode before host files are removed. Set `SetupIconFile` and shortcut icon to `assets\test-system.ico`.

- [ ] **Step 5: Verify GREEN and compile installer**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_inno_installer_contract.py -q
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --filter "FullyQualifiedName~DataDeletionGuard"
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\TestSystem.iss
```

Expected: tests PASS and ISCC creates a versioned setup EXE.

- [ ] **Step 6: Commit**

```powershell
git add installer/TestSystem.iss tests/test_inno_installer_contract.py desktop-host/src/TestSystem.Desktop/Uninstall desktop-host/src/TestSystem.Desktop/Program.cs desktop-host/tests/TestSystem.Desktop.Tests/DataDeletionGuardTests.cs
git commit -m "build: add selectable Windows installer"
```

## Task 11: Add prerequisite acquisition, unified build and artifact audit

**Files:**

- Create: `packaging/prerequisites.ps1`
- Create: `packaging/build_installer.ps1`
- Create: `packaging/verify_installer_artifact.py`
- Create: `tests/test_verify_installer_artifact.py`
- Modify: `packaging/installer_builder.py`
- Modify: `installer/TestSystem.iss`

- [ ] **Step 1: Write failing artifact-audit tests**

Create synthetic stage trees and manifests. Assert rejection of:

- wrong Python version/architecture;
- version mismatch among `version.json`, manifest and generated Inno include;
- `.venv`, `.env`, user data, model files or absolute build-root strings;
- missing host EXE, Python EXE, source directories or WebView2 prerequisite record;
- unpinned base requirements;
- missing or malformed SHA-256 fields.

Assert a valid synthetic image passes and emits a JSON report.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_verify_installer_artifact.py -q
```

Expected: FAIL because verifier does not exist.

- [ ] **Step 3: Implement prerequisite acquisition**

`packaging/prerequisites.ps1` downloads the official Microsoft x64 Evergreen Standalone Runtime from:

```text
https://go.microsoft.com/fwlink/p/?LinkId=2124703
```

to `.cache\prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe`. Validate:

- Authenticode status is `Valid`;
- signer subject contains `Microsoft Corporation`;
- PE architecture is x64;
- file version is readable.

Write `.cache\prerequisites\webview2-runtime.json` containing resolved URL, file version, size and SHA-256. Support `-Offline` to require and revalidate an existing cached file without network access.

- [ ] **Step 4: Implement unified build script**

`packaging/build_installer.ps1` parameters:

```powershell
param(
  [string]$OutputRoot = "dist-installer",
  [string]$PythonHome = "",
  [string]$FfmpegBin = "",
  [string]$LibreOfficePath = "",
  [string]$CertificateThumbprint = "",
  [switch]$OfflinePrerequisites,
  [switch]$SkipTests
)
```

Default flow:

1. require clean version syntax and locate/acquire exact CPython 3.13.10 x64 with `uv`;
2. run Python and JS tests unless `-SkipTests` is explicitly used for local diagnostics;
3. restore locked NuGet packages and run .NET tests;
4. publish host self-contained x64 with version properties from `version.json`;
5. stage clean install image;
6. acquire or validate WebView2 prerequisite;
7. generate `installer/includes/version.iss` containing app/file versions and staging path;
8. run artifact audit;
9. compile Inno Setup;
10. move final file to `dist-installer\Test-System-Setup-<version>-x64.exe`;
11. write sibling `.sha256` and `build-manifest.json` with all tool/runtime versions and source commit.

When `-CertificateThumbprint` is supplied, sign the published desktop EXE before staging and the final installer after compilation with the Windows SDK `signtool.exe`, SHA-256 digest and RFC 3161 timestamp, then require `Get-AuthenticodeSignature` status `Valid`. When omitted, record `codeSigned: false` in the build manifest and print a warning; do not pretend the artifact is signed.

Any failure returns non-zero and leaves no file at the final installer path. Build into a temporary versioned directory and promote only after audit and ISCC succeed.

- [ ] **Step 5: Implement and verify artifact auditor**

Required CLI:

```powershell
.\.venv\Scripts\python.exe packaging\verify_installer_artifact.py `
  --stage .build\installer\Test-System `
  --version-file version.json `
  --webview-manifest .cache\prerequisites\webview2-runtime.json `
  --report .build\installer\artifact-audit.json
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_verify_installer_artifact.py tests\test_installer_builder.py tests\test_portable_builder.py -q
```

Expected: PASS.

- [ ] **Step 6: Build a real installer**

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

Expected outputs:

```text
dist-installer/Test-System-Setup-1.0.0-x64.exe
dist-installer/Test-System-Setup-1.0.0-x64.exe.sha256
dist-installer/build-manifest.json
```

- [ ] **Step 7: Commit**

```powershell
git add packaging/prerequisites.ps1 packaging/build_installer.ps1 packaging/verify_installer_artifact.py packaging/installer_builder.py installer/TestSystem.iss tests/test_verify_installer_artifact.py
git commit -m "build: automate audited Windows installer releases"
```

## Task 12: Document release workflow and run the release gate

**Files:**

- Create: `docs/releasing-windows.md`
- Modify: `README.md`
- Modify: `packaging/README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write the maintainer runbook**

Document prerequisites (`uv`, .NET 8 SDK, Inno Setup 6, optional ffmpeg/LibreOffice sources), exact build command, offline prerequisite cache behavior, version bump rules, changelog format, outputs, SHA-256 verification, optional code-signing hook, MinerU compatibility gate and rollback procedure.

Include this release checklist verbatim as checkboxes:

```markdown
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
```

Update README user instructions to point ordinary users to the setup EXE and keep source/portable sections clearly labeled for developers.

- [ ] **Step 2: Run complete automated verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests rag-anything-api\tests ai-tutor-system\tests -q
node ai-tutor-system\tests\test_frontend_history_actions.js
node ai-tutor-system\tests\test_dropdown_style_unification.js
node ai-tutor-system\tests\test_custom_scenario_persistence.js
node ai-tutor-system\tests\test_knowledge_chat_dropdown.js
node ai-tutor-system\tests\test_knowledge_chat_markdown.js
node ai-tutor-system\tests\test_knowledge_chat_stream.js
node ai-tutor-system\tests\test_model_settings_overview_refresh.js
node ai-tutor-system\tests\test_tutor_database_dropdown.js
node ai-tutor-system\tests\test_tutor_evaluation_card_css.js
node ai-tutor-system\tests\test_workspace_page_frame.js
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api packaging
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --no-restore
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

Expected: every command exits 0 and final installer/hash/manifest exist.

- [ ] **Step 3: Execute clean-machine acceptance matrix**

Use disposable Windows 10 x64 and Windows 11 x64 VMs with no preinstalled WebView2 runtime for the first case. Record OS build, installer hash, program/data paths, installed WebView2 version, PIDs before/after close, port checks, download results, upgrade result, uninstall choice and MinerU result in `dist-installer/acceptance-<version>.md` (artifact only; do not commit machine-specific report).

Required cases:

1. disconnected network, default paths, base app install/start/close/download;
2. disconnected network, Chinese and spaces in both custom paths;
3. repeated double-click activates one instance;
4. foreign listener on 8002 and separately 8003 is reported and not killed;
5. upgrade from previous installer preserves data and selected path;
6. uninstall No retains data, reinstall reconnects it;
7. uninstall Yes deletes only selected data root;
8. MinerU option while offline fails safely, online retry succeeds, Pipeline model is present, scanned sample parses.

- [ ] **Step 4: Update changelog from Unreleased to 1.0.0 only after acceptance passes**

Move verified entries under a dated `1.0.0` heading. If acceptance has any release-blocking failure, leave entries under `Unreleased`, fix via a new TDD cycle and rebuild; do not describe the installer as released.

- [ ] **Step 5: Commit documentation and release metadata**

```powershell
git add README.md packaging/README.md docs/releasing-windows.md CHANGELOG.md
git commit -m "docs: add Windows installer release runbook"
```

## Final verification before handoff

The implementing agent must use `superpowers:verification-before-completion` and report fresh output for:

```powershell
git status --short
git log -12 --oneline
.\.venv\Scripts\python.exe -m pytest tests rag-anything-api\tests ai-tutor-system\tests -q
.\.venv\Scripts\python.exe -m compileall -q ai-tutor-system rag-anything-api packaging
dotnet test desktop-host\TestSystem.Desktop.sln -c Release --no-restore
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -OfflinePrerequisites
Get-FileHash dist-installer\Test-System-Setup-1.0.0-x64.exe -Algorithm SHA256
```

Handoff must state:

- exact installer path and SHA-256;
- automated test totals;
- Windows 10/11 VM acceptance results;
- actual WebView2 Runtime version packaged;
- whether MinerU 3.3.1 + CPython 3.13.10 compatibility gate passed;
- any code-signing limitation;
- whether the worktree contains unrelated pre-existing changes.
