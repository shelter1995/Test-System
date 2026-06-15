param(
    [string]$OutputRoot = "dist-portable",
    [string]$PythonHome = "",
    [string]$FfmpegBin = "",
    [string]$LibreOfficePath = "",
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Builder = Join-Path $PSScriptRoot "portable_builder.py"
$RequiredPython = "3.13.10"

if (-not (Test-Path $Builder)) {
    throw "Portable builder was not found: $Builder"
}

if (-not $PythonHome) {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is required on the build machine to acquire Python $RequiredPython."
    }

    $PythonExe = (& uv python find $RequiredPython 2>$null | Select-Object -First 1)
    if (-not $PythonExe) {
        Write-Host "Python $RequiredPython was not found. Installing it on the build machine..."
        & uv python install $RequiredPython
        if ($LASTEXITCODE -ne 0) {
            throw "uv python install $RequiredPython failed."
        }
        $PythonExe = (& uv python find $RequiredPython | Select-Object -First 1)
    }
    if (-not $PythonExe) {
        throw "Unable to locate Python $RequiredPython after installation."
    }
    $PythonHome = Split-Path -Parent $PythonExe
}

$PackagePython = Join-Path $PythonHome "python.exe"
if (-not (Test-Path $PackagePython)) {
    throw "Python executable was not found: $PackagePython"
}

$DetectedVersion = & $PackagePython -c "import platform; print(platform.python_version())"
if ($DetectedVersion.Trim() -ne $RequiredPython) {
    throw "Portable package requires Python $RequiredPython, got $DetectedVersion."
}

$Args = @(
    $Builder,
    "--root", $Root,
    "--output-root", $OutputRoot,
    "--python-home", $PythonHome
)

if ($FfmpegBin) {
    $Args += @("--ffmpeg-bin", $FfmpegBin)
}
if ($LibreOfficePath) {
    $Args += @("--libreoffice-path", $LibreOfficePath)
}
if ($NoArchive) {
    $Args += "--no-archive"
}

& $PackagePython @Args
if ($LASTEXITCODE -ne 0) {
    throw "Portable package build failed."
}
