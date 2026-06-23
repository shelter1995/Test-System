#define MyAppId "{{D1CF6B3D-77B3-4BFC-A2B1-BE0A8A7CB35D}"
#define MyAppName "智学工作台"
#define MyAppExeName "TestSystem.exe"
#include "includes\version.iss"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=智学工作台
DefaultDirName={localappdata}\Programs\智学工作台
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=智学工作台-Setup-{#MyAppVersion}-x64
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
Name: "chinesesimp"; MessagesFile: "languages\ChineseSimplified.isl"

[Files]
Source: "..\.build\installer\Test-System\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\.cache\prerequisites\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{autoprograms}\智学工作台"; Filename: "{app}\TestSystem.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\test-system.ico"
Name: "{autodesktop}\智学工作台"; Filename: "{app}\TestSystem.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\test-system.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "正在安装 Microsoft Edge WebView2 Runtime..."; Flags: waituntilterminated
Filename: "{app}\TestSystem.exe"; Description: "启动 智学工作台"; Flags: nowait postinstall skipifsilent
Filename: "{app}\TestSystem.exe"; Parameters: "--install-mineru"; Description: "安装 MinerU 增强解析组件"; Flags: nowait postinstall skipifsilent unchecked

[Code]
function CreateInstallId: string;
var
  TypeLib: Variant;
  GuidValue: string;
begin
  TypeLib := CreateOleObject('Scriptlet.TypeLib');
  GuidValue := TypeLib.Guid;
  Result := Copy(GuidValue, 1, 38);
  if (Length(Result) <> 38) or (Copy(Result, 1, 1) <> '{') or (Copy(Result, 38, 1) <> '}') then
    RaiseException('无法生成有效安装标识，请重新运行安装程序。');
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
    if not RegQueryStringValue(HKCU, 'Software\ZhiXueWorkbench', 'InstallId', CurrentInstallId) then
    begin
      CurrentInstallId := CreateInstallId;
    end;
  end;

  ExistingDataDir := '';
  RegQueryStringValue(HKCU, 'Software\ZhiXueWorkbench', 'DataDir', ExistingDataDir);
  SelectedDataDir := NormalizeDir('{localappdata}\智学工作台\Data');

  DataDirPage := CreateInputDirPage(
    wpSelectDir,
    '选择智学工作台数据存储目录',
    '智学工作台应该把运行数据保存在哪里？',
    '安装程序会在升级时保留此目录，卸载时默认也会保留。',
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
      MsgBox('请选择绝对路径作为数据存储目录。', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not ProbeWritableDirectory(Candidate) then
    begin
      MsgBox('所选数据存储目录不可写，请选择其他目录。', mbError, MB_OK);
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
  RegWriteStringValue(HKCU, 'Software\ZhiXueWorkbench', 'DataDir', SelectedDataDir);
  RegWriteStringValue(HKCU, 'Software\ZhiXueWorkbench', 'InstallId', CurrentInstallId);
  RegWriteStringValue(HKCU, 'Software\ZhiXueWorkbench', 'Version', '{#MyAppVersion}');
  SetPreviousData('DataDir', SelectedDataDir, '');
  SetPreviousData('InstallId', CurrentInstallId, '');
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
  RegQueryStringValue(HKCU, 'Software\ZhiXueWorkbench', 'DataDir', UninstallDataDir);
  RegQueryStringValue(HKCU, 'Software\ZhiXueWorkbench', 'InstallId', UninstallInstallId);

  if (UninstallDataDir <> '') and (UninstallInstallId <> '') then
  begin
    DeleteDataOnUninstall :=
      MsgBox(
        '是否同时删除智学工作台的用户数据目录？' + #13#10 + #13#10 +
        UninstallDataDir + #13#10 + #13#10 +
        '选择“否”将保留知识库、配置、生成文件和增强解析组件。',
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
      MsgBox('无法启动智学工作台安全数据删除程序，已保留数据目录。', mbError, MB_OK);
    end
    else if ResultCode <> 0 then
    begin
      MsgBox('智学工作台拒绝删除该数据目录，已保留数据。', mbError, MB_OK);
    end;
  end;
end;
