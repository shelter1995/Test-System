from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "TestSystem.iss"


def _script() -> str:
    assert SCRIPT.exists(), "installer/TestSystem.iss must exist"
    return SCRIPT.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(";"))


def test_setup_identity_and_low_privilege_install_location():
    text = _script()

    assert '#define MyAppId "{{D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D}"' in text
    assert '#define MyAppName "Test-System"' in text
    assert '#include "includes\\version.iss"' in text
    assert "AppId={#MyAppId}" in text
    assert "DefaultDirName={localappdata}\\Programs\\Test-System" in text
    assert "PrivilegesRequired=lowest" in text
    assert "ArchitecturesAllowed=x64compatible" in text
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in text


def test_data_directory_page_defaults_to_local_app_data_and_persists_install_identity():
    text = _script()

    assert "CreateInputDirPage" in text
    assert "{localappdata}\\Test-System\\Data" in text
    assert "RegQueryStringValue(HKCU, 'Software\\Test-System', 'DataDir'" in text
    assert "RegWriteStringValue(HKCU, 'Software\\Test-System', 'DataDir'" in text
    assert "RegWriteStringValue(HKCU, 'Software\\Test-System', 'InstallId'" in text
    assert "RegWriteStringValue(HKCU, 'Software\\Test-System', 'Version'" in text
    assert "{app}\\install-location.json" in text
    assert "{code:GetDataConfigPath}" in text
    assert "SaveUtf8Json" in text
    assert re.search(r"ProbeWritableDirectory\s*\(", text)
    assert re.search(r"RenameFile\s*\(", text)
    assert re.search(r"DeleteFile\s*\(", text)


def test_output_base_filename_includes_x64_architecture():
    text = _script()
    assert r"OutputBaseFilename=Test-System-Setup-{#MyAppVersion}-x64" in text


def test_output_dir_uses_installer_output_dir_define():
    text = _script()
    assert r"OutputDir={#InstallerOutputDir}" in text


def test_shortcuts_target_desktop_host_exe_with_icon_and_never_batch_files():
    text = _strip_comments(_script())

    assert r'Filename: "{app}\TestSystem.exe"' in text
    assert r'IconFilename: "{app}\assets\test-system.ico"' in text
    assert r'Name: "{autoprograms}\Test-System"' in text
    assert r'Name: "{autodesktop}\Test-System"' in text
    assert ".bat" not in text.lower()


def test_bundles_files_and_runs_webview2_x64_standalone_silently():
    text = _script()

    assert r'Source: "..\.build\installer\Test-System\*"' in text
    assert "recursesubdirs" in text
    assert r"MicrosoftEdgeWebView2RuntimeInstallerX64.exe" in text
    assert r'DestDir: "{tmp}"' in text
    assert "deleteafterinstall" in text
    assert r'Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"' in text
    assert r'Parameters: "/silent /install"' in text


def test_finish_page_offers_main_app_and_optional_mineru_installer():
    text = _script()

    assert r'Description: "Launch Test-System"' in text
    assert r'Filename: "{app}\TestSystem.exe"' in text
    assert r'Description: "Install MinerU enhanced parsing components"' in text
    assert r'Parameters: "--install-mineru"' in text
    assert "postinstall" in text


def test_upgrade_checks_running_host_and_preserves_recorded_data_dir():
    text = _script()

    assert "CheckForRunningApp" in text
    assert "TestSystem.exe" in text
    assert "InitializeSetup" in text
    assert "RegQueryStringValue(HKCU, 'Software\\Test-System', 'DataDir'" in text
    assert "ExistingDataDir" in text
    assert "DataDirPage.Values[0] := ExistingDataDir" in text


def test_uninstall_keeps_data_by_default_and_deletes_only_after_explicit_confirmation():
    text = _script()

    assert "InitializeUninstall" in text
    assert "DeleteDataOnUninstall := False" in text
    assert "MB_DEFBUTTON2" in text
    assert "--delete-data" in text
    assert "--install-id" in text
    assert "Exec(ExpandConstant('{app}\\TestSystem.exe')" in text
    assert "CurUninstallStep = usUninstall" in text
    assert "DeleteDataOnUninstall" in text
