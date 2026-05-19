$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Target = Join-Path $Root "start_services.bat"
$Icon = Join-Path $Root "assets\test-system.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Test-System.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = $Root
$Shortcut.IconLocation = $Icon
$Shortcut.Description = "启动 Test-System AI 话术陪练与 RAG 知识库"
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath"
