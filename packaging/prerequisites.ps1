param(
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Off

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PrereqDir = Join-Path $RepoRoot ".cache\prerequisites"
$InstallerName = "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
$InstallerPath = Join-Path $PrereqDir $InstallerName
$ManifestPath = Join-Path $PrereqDir "webview2-runtime.json"
$DownloadUrl = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

function Write-Status {
    param([string]$Message)
    Write-Host "[prerequisites] $Message"
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

    if (Test-Path $InstallerPath -PathType Leaf) {
        Write-Status "Existing installer found. Removing before re-download."
        Remove-Item $InstallerPath -Force
    }

    try {
        Write-Status "Downloading from Microsoft (this may take several minutes)..."
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")
        $wc.DownloadFile($DownloadUrl, $InstallerPath)
        $wc.Dispose()
    } catch {
        Write-Error "Failed to download WebView2 Runtime: $_"
        exit 1
    }

    if (-not (Test-Path $InstallerPath -PathType Leaf)) {
        Write-Error "Download did not produce a file at $InstallerPath"
        exit 1
    }

    $fileSize = (Get-Item $InstallerPath).Length
    if ($fileSize -lt 10MB) {
        Write-Error "Downloaded file is too small ($([math]::Round($fileSize / 1KB, 0)) KB). The download may have been incomplete or redirected to an HTML page. Try manually downloading from https://developer.microsoft.com/en-us/microsoft-edge/webview2/ and place the Evergreen Standalone Installer at: $InstallerPath"
        exit 1
    }
    Write-Status "Downloaded: $([math]::Round($fileSize / 1MB, 1)) MB"
}

Write-Status "Validating file..."
$signatureResult = "NotChecked"
$signerSubject = "unknown"
try {
    Import-Module -Name Microsoft.PowerShell.Security -ErrorAction Stop -WarningAction SilentlyContinue
    $signature = Get-AuthenticodeSignature -FilePath $InstallerPath -ErrorAction Stop
    $signatureResult = $signature.Status
    $signerSubject = $signature.SignerCertificate.Subject
} catch {
    Write-Status "Warning: Could not verify Authenticode signature: $_"
    $signatureResult = "NotChecked"
}

if ($signatureResult -ne "NotChecked") {
    if ($signatureResult -ne "Valid") {
        Write-Error "WebView2 Runtime Authenticode status is '$signatureResult', expected 'Valid'"
        exit 1
    }
    if ($signerSubject -notmatch "Microsoft Corporation") {
        Write-Error "WebView2 Runtime signer is not Microsoft Corporation: $signerSubject"
        exit 1
    }
    Write-Status "Signature valid, signer: $signerSubject"
} else {
    Write-Status "Authenticode check skipped (module unavailable). File version check will serve as validation."
}

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
    if ($machineType -ne 0x8664 -and $machineType -ne 0x014C) {
        Write-Error "WebView2 Runtime PE architecture is $machineName (0x$($machineType.ToString('X4'))), expected AMD64 or I386 bootstrapper"
        exit 1
    }
    if ($machineType -eq 0x014C) {
        Write-Status "PE architecture is I386 (universal bootstrapper, will install x64 runtime on x64 systems)"
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

$sha256 = ((certutil -hashfile $InstallerPath SHA256 | Select-Object -Index 1).Trim() -replace '\s+', '')
$fileSize = (Get-Item $InstallerPath).Length

$manifest = @{
    name = "Microsoft Edge WebView2 Runtime"
    url = $DownloadUrl
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
