param(
    [string]$OutputRoot = "dist-portable"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$PackageName = "Test-System-Portable"
$OutDir = Join-Path $Root $OutputRoot
$PackageDir = Join-Path $OutDir $PackageName

if (Test-Path $PackageDir) {
    Remove-Item $PackageDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

$Include = @(
    "ai-tutor-system",
    "rag-anything-api",
    "assets",
    "packaging",
    "README.md",
    "SETUP.md",
    "CHANGELOG.md",
    "使用说明.md",
    "部署说明.md",
    "rag_database_guide.md",
    "requirements-dev.txt",
    "start_services.bat"
)

foreach ($Item in $Include) {
    $Source = Join-Path $Root $Item
    $Target = Join-Path $PackageDir $Item
    if (Test-Path $Source) {
        Copy-Item $Source $Target -Recurse -Force
    }
}

$Venv = Join-Path $Root ".venv"
if (Test-Path $Venv) {
    Copy-Item $Venv (Join-Path $PackageDir ".venv") -Recurse -Force
}

$RemovePaths = @(
    "rag-anything-api\storage",
    "rag-anything-api\output",
    "ai-tutor-system\tutor_data",
    ".pytest_cache",
    "__pycache__"
)

foreach ($Relative in $RemovePaths) {
    Get-ChildItem $PackageDir -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*$Relative*" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

$ZipPath = Join-Path $OutDir "$PackageName.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force
Write-Host "Portable package created: $ZipPath"
