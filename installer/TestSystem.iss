#define MyAppId "{{D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D}"
#define MyAppName "Test-System"
#define MyAppExeName "TestSystem.exe"
#include "includes\version.iss"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Test-System
DefaultDirName={localappdata}\Programs\Test-System
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=Test-System-Setup-{#MyAppVersion}-x64
OutputDir={#InstallerOutputDir}
SetupIconFile=..\assets\test-system.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\assets\test-system.ico
CloseApplications=no
AppMutex={#MyAppId}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\.build\installer\Test-System\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\.cache\prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{autoprograms}\Test-System"; Filename: "{app}\TestSystem.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\test-system.ico"
Name: "{autodesktop}\Test-System"; Filename: "{app}\TestSystem.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\test-system.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Flags: waituntilterminated
Filename: "{app}\TestSystem.exe"; Description: "Launch Test-System"; Flags: nowait postinstall skipifsilent
Filename: "{app}\TestSystem.exe"; Parameters: "--install-mineru"; Description: "Install MinerU enhanced parsing components"; Flags: nowait postinstall skipifsilent unchecked

[Code]
function GenerateRandomHex(Count: Integer): string;
var
  I: Integer;
  Chars: string;
begin
  Chars := '0123456789abcdef';
  Result := '';
  for I := 1 to Count do
    Result := Result + Copy(Chars, Random(16) + 1, 1);
end;

function CreateInstallId: string;
begin
  Randomize;
  Result :=
    GenerateRandomHex(8) + '-' +
    GenerateRandomHex(4) + '-' +
    GenerateRandomHex(4) + '-' +
    GenerateRandomHex(4) + '-' +
    GenerateRandomHex(12);
end;

var
  DataDirPage: TInputDirWizardPage;
  ExistingDataDir: string;
  SelectedDataDir: string;
  CurrentInstallId: string;
  DeleteDataOnUninstall: Boolean;
  UninstallDataDir: string;
  UninstallInstallId: string;

function NormalizeDir(Value: string): string;
begin
  Result := RemoveBackslash(ExpandConstant(Value));
end;

function IsAbsolutePath(Value: string): Boolean;
begin
  Result :=
    ((Length(Value) >= 3) and (Value[2] = ':') and ((Value[3] = '\') or (Value[3] = '/'))) or
    ((Length(Value) >= 2) and (Value[1] = '\') and (Value[2] = '\'));
end;

function JsonEscape(Value: string): string;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

function BuildInstallJson(DataDir: string; InstallId: string): string;
begin
  Result := '{"dataDir":"' + JsonEscape(DataDir) + '","installId":"' + JsonEscape(InstallId) + '"}';
end;

procedure SaveUtf8Json(FileName: string; Contents: string);
begin
  ForceDirectories(ExtractFileDir(FileName));
  if not SaveStringToFile(FileName, Contents, False) then
    RaiseException('Failed to write: ' + FileName);
end;

function ProbeWritableDirectory(DirName: string): Boolean;
var
  ProbeFile: string;
  RenamedFile: string;
begin
  Result := False;
  ProbeFile := AddBackslash(DirName) + '.test-system-write-probe-' + CurrentInstallId + '.tmp';
  RenamedFile := ProbeFile + '.renamed';

  if not ForceDirectories(DirName) then
  begin
    Exit;
  end;

  if not SaveStringToFile(ProbeFile, 'ok', False) then
  begin
    Exit;
  end;

  if not RenameFile(ProbeFile, RenamedFile) then
  begin
    DeleteFile(ProbeFile);
    Exit;
  end;

  DeleteFile(RenamedFile);
  Result := True;
end;

function GetDataDir(Param: string): string;
begin
  Result := SelectedDataDir;
end;

function GetDataConfigPath(Param: string): string;
begin
  Result := AddBackslash(SelectedDataDir) + 'config\install.json';
end;

function GetInstallId(Param: string): string;
begin
  Result := CurrentInstallId;
end;

procedure InitializeWizard();
begin
  CurrentInstallId := GetPreviousData('InstallId', '');
  if CurrentInstallId = '' then
  begin
    if not RegQueryStringValue(HKCU, 'Software\Test-System', 'InstallId', CurrentInstallId) then
    begin
      CurrentInstallId := CreateInstallId;
    end;
  end;

  ExistingDataDir := '';
  RegQueryStringValue(HKCU, 'Software\Test-System', 'DataDir', ExistingDataDir);
  SelectedDataDir := NormalizeDir('{localappdata}\Test-System\Data');

  DataDirPage := CreateInputDirPage(
    wpSelectDir,
    'Choose Test-System data directory',
    'Where should Test-System store runtime data?',
    'Setup will preserve this directory during upgrades and safe uninstall keeps it by default.',
    False,
    '');
  DataDirPage.Add('');

  if ExistingDataDir <> '' then
  begin
    DataDirPage.Values[0] := ExistingDataDir;
    SelectedDataDir := ExistingDataDir;
  end
  else
  begin
    DataDirPage.Values[0] := SelectedDataDir;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Candidate: string;
begin
  Result := True;
  if CurPageID = DataDirPage.ID then
  begin
    Candidate := NormalizeDir(DataDirPage.Values[0]);
    if not IsAbsolutePath(Candidate) then
    begin
      MsgBox('Please choose an absolute data directory path.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not ProbeWritableDirectory(Candidate) then
    begin
      MsgBox('The selected data directory is not writable.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    SelectedDataDir := Candidate;
  end;
end;

procedure RegisterInstallLocation();
var
  Json: string;
begin
  Json := BuildInstallJson(SelectedDataDir, CurrentInstallId);
  SaveUtf8Json(ExpandConstant('{app}\install-location.json'), Json);
  SaveUtf8Json(ExpandConstant('{code:GetDataConfigPath}'), Json);
  RegWriteStringValue(HKCU, 'Software\Test-System', 'DataDir', SelectedDataDir);
  RegWriteStringValue(HKCU, 'Software\Test-System', 'InstallId', CurrentInstallId);
  RegWriteStringValue(HKCU, 'Software\Test-System', 'Version', '{#MyAppVersion}');
  SetPreviousData('DataDir', SelectedDataDir);
  SetPreviousData('InstallId', CurrentInstallId);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RegisterInstallLocation();
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  DeleteDataOnUninstall := False;
  RegQueryStringValue(HKCU, 'Software\Test-System', 'DataDir', UninstallDataDir);
  RegQueryStringValue(HKCU, 'Software\Test-System', 'InstallId', UninstallInstallId);

  if (UninstallDataDir <> '') and (UninstallInstallId <> '') then
  begin
    DeleteDataOnUninstall :=
      MsgBox(
        'Do you also want to delete the Test-System data directory?' + #13#10 + #13#10 +
        UninstallDataDir + #13#10 + #13#10 +
        'Choose No to keep your data.',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2) = IDYES;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if (CurUninstallStep = usUninstall) and DeleteDataOnUninstall then
  begin
    if not Exec(ExpandConstant('{app}\TestSystem.exe'),
      '--delete-data "' + UninstallDataDir + '" --install-id ' + UninstallInstallId,
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode) then
    begin
      MsgBox('Test-System could not start the safe data deletion helper. Your data was kept.', mbError, MB_OK);
    end
    else if ResultCode <> 0 then
    begin
      MsgBox('Test-System refused to delete the data directory. Your data was kept.', mbError, MB_OK);
    end;
  end;
end;
