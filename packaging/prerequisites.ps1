param(
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PrereqDir = Join-Path $RepoRoot ".cache\prerequisites"
$InstallerName = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
$InstallerPath = Join-Path $PrereqDir $InstallerName
$ManifestPath = Join-Path $PrereqDir "webview2-runtime.json"
$DownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

function Write-Status {
    param([string]$Message)
    Write-Host "[prerequisites] $Message"
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-DownloadUrl {
    try {
        $response = Invoke-WebRequest -Uri $DownloadUrl -Method Head -MaximumRedirection 0 -ErrorAction SilentlyContinue
        if ($response.StatusCode -in @(301, 302, 303, 307, 308)) {
            $resolved = $response.Headers.Location
            if ($resolved -is [array]) { $resolved = $resolved[0] }
            return $resolved
        }
        return $DownloadUrl
    } catch {
        if ($_.Exception.Response.StatusCode -in @(301, 302, 303, 307, 308)) {
            $resolved = $_.Exception.Response.Headers.Location
            if ($resolved -is [array]) { $resolved = $resolved[0] }
            return $resolved
        }
        return $DownloadUrl
    }
}

if ($Offline) {
    Write-Status "Offline mode: validating existing prerequisite cache."
    if (-not (Test-Path $InstallerPath -PathType Leaf)) {
        Write-Error "Offline prerequisite check failed: $InstallerPath not found"
        exit 1
    }
    if (-not (Test-Path $ManifestPath -PathType Leaf)) {
        Write-Error "Offline prerequisite check failed: $ManifestPath not found"
        exit 1
    }
    Write-Status "Offline prerequisite cache exists."
} else {
    Write-Status "Acquiring WebView2 Evergreen Standalone Runtime..."
    $null = New-Item -ItemType Directory -Path $PrereqDir -Force

    $resolvedUrl = Resolve-DownloadUrl
    Write-Status "Resolved download URL: $resolvedUrl"

    if (Test-Path $InstallerPath -PathType Leaf) {
        Write-Status "Existing installer found. Removing before re-download."
        Remove-Item $InstallerPath -Force
    }

    try {
        Invoke-WebRequest -Uri $resolvedUrl -OutFile $InstallerPath -UseBasicParsing
    } catch {
        Write-Error "Failed to download WebView2 Runtime: $_"
        exit 1
    }

    if (-not (Test-Path $InstallerPath -PathType Leaf)) {
        Write-Error "Download did not produce a file at $InstallerPath"
        exit 1
    }

    Write-Status "Downloaded: $([math]::Round((Get-Item $InstallerPath).Length / 1MB, 1)) MB"
}

Write-Status "Validating Authenticode signature..."
$signature = Get-AuthenticodeSignature -FilePath $InstallerPath
if ($signature.Status -ne "Valid") {
    Write-Error "WebView2 Runtime Authenticode status is '$($signature.Status)', expected 'Valid'"
    exit 1
}

$signer = $signature.SignerCertificate.Subject
if ($signer -notmatch "Microsoft Corporation") {
    Write-Error "WebView2 Runtime signer is not Microsoft Corporation: $signer"
    exit 1
}
Write-Status "Signature valid, signer: $signer"

Write-Status "Validating PE architecture..."
try {
    $peBytes = [System.IO.File]::ReadAllBytes($InstallerPath)
    if ($peBytes.Length -lt 64) {
        Write-Error "WebView2 Runtime file is too small to be a valid PE"
        exit 1
    }
    $peOffsetBytes = $peBytes[60..63]
    $peOffset = [BitConverter]::ToInt32($peOffsetBytes, 0)
    if ($peOffset -lt 64 -or $peOffset -ge $peBytes.Length) {
        Write-Error "WebView2 Runtime has an invalid PE header offset"
        exit 1
    }
    $machineTypeBytes = $peBytes[($peOffset + 4)..($peOffset + 5)]
    $machineType = [BitConverter]::ToUInt16($machineTypeBytes, 0)
    $machineName = switch ($machineType) {
        0x8664 { "AMD64" }
        0x014C { "I386" }
        0xAA64 { "ARM64" }
        default { "Unknown ($machineType)" }
    }
    if ($machineType -ne 0x8664) {
        Write-Error "WebView2 Runtime PE architecture is $machineName, expected AMD64"
        exit 1
    }
    Write-Status "PE architecture: $machineName"
} catch [Exception] {
    Write-Error "Failed to validate PE architecture: $_"
    exit 1
}

Write-Status "Reading file version..."
$fileVersion = (Get-Item $InstallerPath).VersionInfo.FileVersion
if (-not $fileVersion) {
    $fileVersion = "unknown"
}
Write-Status "File version: $fileVersion"

$sha256 = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash
$fileSize = (Get-Item $InstallerPath).Length
$resolvedUrl = Resolve-DownloadUrl

$manifest = @{
    name = "Microsoft Edge WebView2 Runtime"
    url = $resolvedUrl
    file = $InstallerName
    version = $fileVersion
    architecture = "AMD64"
    size = $fileSize
    sha256 = $sha256
    signerSubject = $signer
} | ConvertTo-Json -Depth 4

$manifest | Set-Content -Path $ManifestPath -Encoding UTF8
Write-Status "Manifest written to: $ManifestPath"
Write-Status "Prerequisite acquisition complete."
