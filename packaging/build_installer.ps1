param(
    [string]$OutputRoot = "dist-installer",
    [string]$PythonHome = "",
    [string]$FfmpegBin = "",
    [string]$LibreOfficePath = "",
    [string]$CertificateThumbprint = "",
    [switch]$OfflinePrerequisites,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BuildRoot = Join-Path $RepoRoot ".build"
$StagingRoot = Join-Path $BuildRoot "installer"
$LogsRoot = Join-Path $BuildRoot "build-logs"
$DesktopPublish = Join-Path $BuildRoot "desktop-smoke"
$CacheRoot = Join-Path $RepoRoot ".cache"
$PrereqDir = Join-Path $CacheRoot "prerequisites"
$VersionFile = Join-Path $RepoRoot "version.json"
$InstallerDir = Join-Path $RepoRoot "installer"
$FinalDir = Join-Path $RepoRoot $OutputRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$VersionModule = Join-Path $RepoRoot "packaging\product_version.py"
$InstallerBuilder = Join-Path $RepoRoot "packaging\installer_builder.py"
$Auditor = Join-Path $RepoRoot "packaging\verify_installer_artifact.py"
$PrereqScript = Join-Path $RepoRoot "packaging\prerequisites.ps1"
$IssScript = Join-Path $InstallerDir "TestSystem.iss"
$BuildManifest = $null  # set after version is known

function Write-Step {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Write-Result {
    param([string]$Message, [bool]$Success = $true)
    $color = if ($Success) { "Green" } else { "Red" }
    Write-Host "  -> $Message" -ForegroundColor $color
}

function Invoke-Tool {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [string]$WorkingDir = $RepoRoot
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = $Arguments -join " "
    $psi.WorkingDirectory = $WorkingDir
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        Write-Host $stdout
        Write-Host $stderr
        throw "Command failed with exit code $($process.ExitCode): $Exe $($Arguments -join ' ')"
    }
    return $stdout
}

# ---------------------------------------------------------------------------
# 1. Version parsing
# ---------------------------------------------------------------------------
Write-Step "Parsing product version"

$versionJson = Get-Content $VersionFile -Raw -Encoding UTF8 | ConvertFrom-Json
$ProductVersion = $versionJson.version
if ($ProductVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "version.json must contain MAJOR.MINOR.PATCH, got: $ProductVersion"
}
$FileVersion = "$ProductVersion.0"
$InstallerName = "Test-System-Setup-$ProductVersion-x64.exe"
$InstallerPath = Join-Path $FinalDir $InstallerName
$HashPath = "$InstallerPath.sha256"
$BuildManifest = Join-Path $FinalDir "build-manifest.json"
Write-Result "Version: $ProductVersion (file: $FileVersion)"

# ---------------------------------------------------------------------------
# 2. Locate Python
# ---------------------------------------------------------------------------
Write-Step "Locating CPython 3.13.10 x64"

if (-not $PythonHome) {
    # Look for Python bundled by portable_builder
    $candidate = Join-Path $CacheRoot "python\cpython-3.13.10-windows-x86_64"
    if (Test-Path $candidate) {
        $PythonHome = $candidate
    } else {
        # Try uv-managed Python
        $uvPython = "$env:APPDATA\uv\python\cpython-3.13.10-windows-x86_64-none"
        if (Test-Path $uvPython) {
            $PythonHome = $uvPython
        } else {
            throw "PythonHome not specified and no cached CPython found. Set -PythonHome, run the portable builder first, or install via: uv python install 3.13.10"
        }
    }
}
$PythonHome = (Resolve-Path $PythonHome).Path
$PythonExe = Join-Path $PythonHome "python.exe"
if (-not (Test-Path $PythonExe -PathType Leaf)) {
    throw "Python executable not found at $PythonExe"
}
Write-Result "Python: $PythonHome"

# ---------------------------------------------------------------------------
# 3. Run tests (unless skipped)
# ---------------------------------------------------------------------------
if (-not $SkipTests) {
    Write-Step "Running Python tests"
    $pythonTestArgs = @("-m", "pytest", "tests", "rag-anything-api\tests", "ai-tutor-system\tests", "-q")
    $pythonResult = Invoke-Tool -Exe $Python -Arguments $pythonTestArgs
    Write-Result "Python tests passed"

    Write-Step "Running JavaScript tests"
    $nodeTests = @(
        "ai-tutor-system\tests\test_frontend_history_actions.js",
        "ai-tutor-system\tests\test_dropdown_style_unification.js",
        "ai-tutor-system\tests\test_custom_scenario_persistence.js",
        "ai-tutor-system\tests\test_knowledge_chat_dropdown.js",
        "ai-tutor-system\tests\test_knowledge_chat_markdown.js",
        "ai-tutor-system\tests\test_knowledge_chat_stream.js",
        "ai-tutor-system\tests\test_model_settings_overview_refresh.js",
        "ai-tutor-system\tests\test_tutor_database_dropdown.js",
        "ai-tutor-system\tests\test_tutor_evaluation_card_css.js",
        "ai-tutor-system\tests\test_workspace_page_frame.js"
    )
    foreach ($test in $nodeTests) {
        $testPath = Join-Path $RepoRoot $test
        if (Test-Path $testPath) {
            Invoke-Tool -Exe "node" -Arguments @($testPath)
            Write-Host "  JS: $test passed"
        } else {
            Write-Host "  JS: $test (skipped - not found)"
        }
    }
    Write-Result "JavaScript tests passed"

    Write-Step "Running .NET tests"
    Invoke-Tool -Exe "dotnet" -Arguments @("restore", "desktop-host\TestSystem.Desktop.sln", "--locked-mode")
    Invoke-Tool -Exe "dotnet" -Arguments @("test", "desktop-host\TestSystem.Desktop.sln", "-c", "Release")
    Write-Result ".NET tests passed"
} else {
    Write-Result "Tests skipped (-SkipTests)"
}

# ---------------------------------------------------------------------------
# 4. Publish desktop host
# ---------------------------------------------------------------------------
Write-Step "Publishing desktop host"

$publishDir = Join-Path $BuildRoot "desktop-publish"
if (Test-Path $publishDir) {
    Remove-Item $publishDir -Recurse -Force
}
$publishArgs = @(
    "publish", "desktop-host\src\TestSystem.Desktop\TestSystem.Desktop.csproj",
    "-c", "Release",
    "-r", "win-x64",
    "--self-contained", "true",
    "-o", $publishDir
)
Invoke-Tool -Exe "dotnet" -Arguments $publishArgs
$publishExe = Join-Path $publishDir "TestSystem.exe"
if (-not (Test-Path $publishExe -PathType Leaf)) {
    throw "Publish did not produce TestSystem.exe at $publishExe"
}
Write-Result "Desktop host published to: $publishDir"

# ---------------------------------------------------------------------------
# 4b. Sign desktop host (if certificate specified)
# ---------------------------------------------------------------------------
$codeSigned = $false
if ($CertificateThumbprint) {
    Write-Step "Signing desktop host EXE"
    $signArgs = @(
        "sign", "/fd", "SHA256",
        "/sha1", $CertificateThumbprint,
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        $publishExe
    )
    Invoke-Tool -Exe "signtool.exe" -Arguments $signArgs
    $sig = Get-AuthenticodeSignature -FilePath $publishExe
    if ($sig.Status -ne "Valid") {
        throw "Desktop host signature is not Valid: $($sig.Status)"
    }
    $codeSigned = $true
    Write-Result "Desktop host signed"
}

# ---------------------------------------------------------------------------
# 5. Stage install image
# ---------------------------------------------------------------------------
Write-Step "Staging install image"

$stageArgs = @(
    $InstallerBuilder,
    "--root", $RepoRoot,
    "--output-root", $StagingRoot,
    "--python-home", $PythonHome,
    "--desktop-publish", $publishDir,
    "--version-file", $VersionFile
)
if ($FfmpegBin) { $stageArgs += @("--ffmpeg-bin", $FfmpegBin) }
if ($LibreOfficePath) { $stageArgs += @("--libreoffice-path", $LibreOfficePath) }

Invoke-Tool -Exe $Python -Arguments $stageArgs
Write-Result "Install image staged to: $StagingRoot"

# ---------------------------------------------------------------------------
# 6. Acquire or validate WebView2 prerequisite
# ---------------------------------------------------------------------------
Write-Step "WebView2 prerequisite"

$prereqArgs = @("-ExecutionPolicy", "Bypass", "-File", $PrereqScript)
if ($OfflinePrerequisites) {
    $prereqArgs += "-Offline"
}
Invoke-Tool -Exe "powershell.exe" -Arguments $prereqArgs
$webviewManifest = Join-Path $PrereqDir "webview2-runtime.json"
$webviewData = Get-Content $webviewManifest -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Result "WebView2 Runtime v$($webviewData.version) ready"

# ---------------------------------------------------------------------------
# 7. Generate version include for Inno Setup
# ---------------------------------------------------------------------------
Write-Step "Generating Inno Setup version include"

$includesDir = Join-Path $InstallerDir "includes"
$null = New-Item -ItemType Directory -Path $includesDir -Force
$versionIss = Join-Path $includesDir "version.iss"
@"
#define MyAppVersion "$ProductVersion"
#define MyAppFileVersion "$FileVersion"
"@ | Set-Content -Path $versionIss -Encoding ASCII
Write-Result "Generated: $versionIss"

# ---------------------------------------------------------------------------
# 8. Run artifact audit
# ---------------------------------------------------------------------------
Write-Step "Auditing install image"

$auditReport = Join-Path $BuildRoot "artifact-audit.json"
$auditArgs = @(
    $Auditor,
    "--stage", (Join-Path $StagingRoot "Test-System"),
    "--version-file", $VersionFile,
    "--webview-manifest", $webviewManifest,
    "--report", $auditReport
)
Invoke-Tool -Exe $Python -Arguments $auditArgs
Write-Result "Artifact audit passed: $auditReport"

# ---------------------------------------------------------------------------
# 9. Compile Inno Setup
# ---------------------------------------------------------------------------
Write-Step "Compiling Inno Setup installer"

$isccExe = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $isccExe -PathType Leaf)) {
    $isccExe = "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $isccExe -PathType Leaf)) {
    throw "Inno Setup 6 ISCC.exe not found. Install Inno Setup 6 or adjust PATH."
}

$isccResult = Invoke-Tool -Exe $isccExe -Arguments @($IssScript) -WorkingDir $RepoRoot
Write-Result "Inno Setup compiled successfully"

# ---------------------------------------------------------------------------
# 9b. Sign final installer (if certificate specified)
# ---------------------------------------------------------------------------
$setupExe = Join-Path $RepoRoot "dist-installer\Test-System-Setup-$ProductVersion-x64.exe"
# Inno Setup's OutputDir is relative; the output goes to the repo root's dist-installer
$setupCandidate = Join-Path $RepoRoot "Output\Test-System-Setup-$ProductVersion.exe"
if (Test-Path $setupCandidate) {
    $null = New-Item -ItemType Directory -Path $FinalDir -Force
    Move-Item $setupCandidate $InstallerPath -Force
}
# Also check if it's directly in the output dir
$setupCandidate2 = Join-Path $RepoRoot "dist-installer\Test-System-Setup-$ProductVersion.exe"
if (Test-Path $setupCandidate2) {
    $null = New-Item -ItemType Directory -Path $FinalDir -Force
    Move-Item $setupCandidate2 $InstallerPath -Force
}

if (-not (Test-Path $InstallerPath -PathType Leaf)) {
    Write-Host "Looking for setup output..."
    $searchResults = Get-ChildItem -Path $RepoRoot -Recurse -Filter "Test-System-Setup-*.exe" -ErrorAction SilentlyContinue
    if ($searchResults) {
        $source = $searchResults[0].FullName
        $null = New-Item -ItemType Directory -Path $FinalDir -Force
        Move-Item $source $InstallerPath -Force
        Write-Result "Found setup at: $InstallerPath"
    } else {
        throw "Inno Setup did not produce the expected output file. Looked for: Test-System-Setup-$ProductVersion*.exe"
    }
}

if ($CertificateThumbprint) {
    Write-Step "Signing final installer"
    $signArgs = @(
        "sign", "/fd", "SHA256",
        "/sha1", $CertificateThumbprint,
        "/tr", "http://timestamp.digicert.com",
        "/td", "SHA256",
        $InstallerPath
    )
    Invoke-Tool -Exe "signtool.exe" -Arguments $signArgs
    $sig = Get-AuthenticodeSignature -FilePath $InstallerPath
    if ($sig.Status -ne "Valid") {
        throw "Installer signature is not Valid: $($sig.Status)"
    }
    $codeSigned = $true
    Write-Result "Installer signed"
}

# ---------------------------------------------------------------------------
# 10. Write SHA-256 and build manifest
# ---------------------------------------------------------------------------
Write-Step "Writing build artifacts"

$hash = ((certutil -hashfile $InstallerPath SHA256 | Select-Object -Index 1).Trim() -replace '\s+', '')
$hash | Set-Content -Path $HashPath -Encoding ASCII

$buildManifest = @{
    product = $ProductVersion
    installer = $InstallerName
    sha256 = $hash
    python_version = "3.13.10"
    python_path = $PythonHome
    webview2_version = $webviewData.version
    codeSigned = $codeSigned
    built_at = (Get-Date -Format "o")
    source_commit = (git -C $RepoRoot rev-parse HEAD)
} | ConvertTo-Json -Depth 3

$buildManifest | Set-Content -Path $BuildManifest -Encoding UTF8

Write-Result "Installer: $InstallerPath"
Write-Result "SHA-256: $hash"
Write-Result "Build manifest: $BuildManifest"

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Build complete: $InstallerName" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
