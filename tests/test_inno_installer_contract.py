from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "TestSystem.iss"
PRODUCT_NAME = "智学工作台"
REGISTRY_KEY = "Software\\ZhiXueWorkbench"


def _script() -> str:
    assert SCRIPT.exists(), "installer/TestSystem.iss must exist"
    return SCRIPT.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(";"))


def test_setup_identity_and_low_privilege_install_location():
    text = _script()

    assert '#define MyAppId "{{D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D}"' in text
    assert f'#define MyAppName "{PRODUCT_NAME}"' in text
    assert '#include "includes\\version.iss"' in text
    assert "AppId={#MyAppId}" in text
    assert f"DefaultDirName={{localappdata}}\\Programs\\{PRODUCT_NAME}" in text
    assert "PrivilegesRequired=lowest" in text
    assert "ArchitecturesAllowed=x64compatible" in text
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in text


def test_data_directory_page_defaults_to_local_app_data_and_persists_install_identity():
    text = _script()

    assert "CreateInputDirPage" in text
    create_install_id = re.search(
        r"function CreateInstallId: string;.*?end;",
        text,
        flags=re.DOTALL,
    ).group(0)
    assert "CreateOleObject('Scriptlet.TypeLib')" in create_install_id
    assert "TypeLib.Guid" in create_install_id
    assert "CreateGUID" not in create_install_id
    assert "GetDateTimeString" not in create_install_id
    assert f"{{localappdata}}\\{PRODUCT_NAME}\\Data" in text
    assert f"RegQueryStringValue(HKCU, '{REGISTRY_KEY}', 'DataDir'" in text
    assert f"RegWriteStringValue(HKCU, '{REGISTRY_KEY}', 'DataDir'" in text
    assert f"RegWriteStringValue(HKCU, '{REGISTRY_KEY}', 'InstallId'" in text
    assert f"RegWriteStringValue(HKCU, '{REGISTRY_KEY}', 'Version'" in text
    assert "{app}\\install-location.json" in text
    assert "{code:GetDataConfigPath}" in text
    assert "SaveUtf8Json" in text
    assert "SaveStringsToUTF8FileWithoutBOM" in text
    assert re.search(r"ProbeWritableDirectory\s*\(", text)
    assert re.search(r"RenameFile\s*\(", text)
    assert re.search(r"DeleteFile\s*\(", text)


def test_output_base_filename_includes_x64_architecture():
    text = _script()
    assert r"OutputBaseFilename=智学工作台-Setup-{#MyAppVersion}-x64" in text


def test_output_dir_uses_installer_output_dir_define():
    text = _script()
    assert r"OutputDir={#InstallerOutputDir}" in text


def test_shortcuts_target_desktop_host_exe_with_icon_and_never_batch_files():
    text = _strip_comments(_script())

    assert r'Filename: "{app}\TestSystem.exe"' in text
    assert r'IconFilename: "{app}\assets\test-system.ico"' in text
    assert rf'Name: "{{autoprograms}}\{PRODUCT_NAME}"' in text
    assert rf'Name: "{{autodesktop}}\{PRODUCT_NAME}"' in text
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

    assert rf'Description: "启动 {PRODUCT_NAME}"' in text
    assert r'Filename: "{app}\TestSystem.exe"' in text
    assert r'Description: "安装 MinerU 增强解析组件"' in text
    assert r'Parameters: "--install-mineru"' in text
    assert "postinstall" in text


def test_installer_visible_text_is_chinese():
    text = _script()

    assert 'Name: "chinesesimp"' in text
    assert 'MessagesFile: "languages\\ChineseSimplified.isl"' in text
    forbidden_visible_text = (
        "Create a desktop shortcut",
        "Additional shortcuts",
        "Installing Microsoft Edge WebView2 Runtime",
        "Please close Test-System",
        "Choose Test-System data directory",
        "Where should Test-System store runtime data",
        "Please choose an absolute data directory path",
        "The selected data directory is not writable",
        "Do you also want to delete",
        "Choose No to keep your data",
    )
    for phrase in forbidden_visible_text:
        assert phrase not in text


def test_upgrade_uses_app_mutex_and_preserves_recorded_data_dir():
    text = _script()

    assert "AppMutex={#MyAppId}" in text
    assert "TestSystem.exe" in text
    assert f"RegQueryStringValue(HKCU, '{REGISTRY_KEY}', 'DataDir'" in text
    assert "ExistingDataDir" in text
    assert "DataDirPage.Values[0] := ExistingDataDir" in text
    assert "procedure RegisterPreviousData(PreviousDataKey: Integer)" in text
    assert "SetPreviousData(PreviousDataKey, 'DataDir', SelectedDataDir)" in text
    assert "SetPreviousData(PreviousDataKey, 'InstallId', CurrentInstallId)" in text
    assert "SetPreviousData('DataDir'" not in text
    assert "SetPreviousData('InstallId'" not in text


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
