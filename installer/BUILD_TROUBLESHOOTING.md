# Windows 安装包构建问题排查指南

本文档记录了构建 Windows exe 安装包过程中遇到的典型错误和解决方案，帮助后续开发避免重复踩坑。

---

## 1. Inno Setup Pascal 脚本兼容性问题

### 1.1 ADODB.Stream 不可用

**问题**: 使用 `CreateOleObject('ADODB.Stream')` 写入 UTF-8 文件时，在某些 Windows 环境下会失败。

**解决方案**: 使用 Inno Setup 内置的 `SaveStringToFile` 函数。

```pascal
// 错误写法
procedure SaveUtf8Json(FileName: string; Contents: string);
var
  Stream: Variant;
begin
  Stream := CreateOleObject('ADODB.Stream');
  Stream.Type := 2;
  Stream.Charset := 'utf-8';
  Stream.Open;
  Stream.WriteText(Contents);
  Stream.SaveToFile(FileName, 2);
  Stream.Close;
end;

// 正确写法
procedure SaveUtf8Json(FileName: string; Contents: string);
begin
  ForceDirectories(ExtractFileDir(FileName));
  if not SaveStringToFile(FileName, Contents, False) then
    RaiseException('Failed to write: ' + FileName);
end;
```

### 1.2 CoCreateGuid 导入失败

**问题**: 通过 `external 'CoCreateGuid@ole32.dll stdcall'` 导入 COM 函数在某些环境下失败。

**解决方案**: 使用 Pascal 的 `Random` 函数生成 GUID。

```pascal
// 错误写法
function CoCreateGuid(out Guid: TGUID): Integer; external 'CoCreateGuid@ole32.dll stdcall';

function CreateInstallId: string;
var
  Guid: TGUID;
begin
  OleCheck(CoCreateGuid(Guid));
  Result := Format('%.8x-%.4x-%.4x-%.2x%.2x-%.2x%.2x%.2x%.2x%.2x%.2x', [
    Guid.D1, Guid.D2, Guid.D3,
    Guid.D4[0], Guid.D4[1], Guid.D4[2], Guid.D4[3],
    Guid.D4[4], Guid.D4[5], Guid.D4[6], Guid.D4[7]]);
end;

// 正确写法
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
```

### 1.3 WMI GetObject 查询失败

**问题**: 使用 `GetObject('winmgmts:\\.\root\cimv2')` 检测运行中的进程在某些环境下失败。

**解决方案**: 使用 Inno Setup 内置的 `AppMutex` 指令。

```pascal
// 错误写法 - 需要大量代码且不可靠
function CheckForRunningApp(): Boolean;
var
  WmiService: Variant;
  Processes: Variant;
begin
  try
    WmiService := GetObject('winmgmts:\\.\root\cimv2');
    Processes := WmiService.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''TestSystem.exe''');
    Result := (Processes.Count > 0);
  except
    Result := False;
  end;
end;

// 正确写法 - 在 [Setup] 段添加一行即可
[Setup]
AppMutex={#MyAppId}
```

---

## 2. PowerShell 5.1 兼容性问题

### 2.1 Set-Content 编码问题

**问题**: `Set-Content` 在 PowerShell 5.1 中处理 UTF-8 编码时行为不一致，可能导致文件损坏。

**解决方案**: 使用 `Out-File` 替代 `Set-Content`。

```powershell
# 错误写法
$content | Set-Content -Path $filePath -Encoding UTF8

# 正确写法
$content | Out-File -FilePath $filePath -Encoding UTF8
```

**注意**: 对于 ASCII 文件也要使用 `Out-File`，确保行为一致。

```powershell
# 错误写法
$versionIss | Set-Content -Path $versionIss -Encoding ASCII

# 正确写法
$versionIss | Out-File -FilePath $versionIss -Encoding ASCII
```

---

## 3. WebView2 相关问题

### 3.1 WebView2 运行时下载失败

**问题**: 下载 WebView2 Evergreen Standalone Installer 时可能遇到重定向、网络超时等问题。

**解决方案**:
1. 使用直接的 CDN URL，不要依赖重定向
2. 添加重试机制
3. 验证下载文件大小（应 > 10MB）

```powershell
# 错误写法 - 依赖重定向解析
$resolvedUrl = Resolve-DownloadUrl  # 复杂的重定向处理逻辑
Invoke-WebRequest -Uri $resolvedUrl -OutFile $InstallerPath

# 正确写法 - 使用直接 URL + 重试 + 文件大小验证
$DownloadUrl = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/..."
Invoke-WebRequest -Uri $DownloadUrl -OutFile $InstallerPath -UseBasicParsing -MaximumRetryCount 3 -RetryIntervalSec 5

$fileSize = (Get-Item $InstallerPath).Length
if ($fileSize -lt 10MB) {
    Write-Error "Downloaded file is too small. The download may have been incomplete."
    exit 1
}
```

### 3.2 WebView2 控件初始化失败

**问题**: WebView2 控件在隐藏状态下初始化会导致挂起。

**解决方案**: 在调用 `EnsureCoreWebView2Async` 之前先设置 `Visible = true`。

```csharp
// 错误写法
private async Task InitializeWebViewAsync()
{
    var environment = await CoreWebView2Environment.CreateAsync(...);
    await webView.EnsureCoreWebView2Async(environment);
    // ... 其他初始化
    webView.Visible = true;  // 太晚了！
}

// 正确写法
private async Task InitializeWebViewAsync()
{
    Directory.CreateDirectory(_layout.WebViewUserData);
    webView.Visible = true;  // 先显示控件
    webView.CreateControl();
    webView.BringToFront();
    mainMenu.BringToFront();

    var environment = await CoreWebView2Environment.CreateAsync(...)
        .WaitAsync(TimeSpan.FromSeconds(30));
    await webView.EnsureCoreWebView2Async(environment)
        .WaitAsync(TimeSpan.FromSeconds(30));
    // ... 其他初始化
}
```

### 3.3 WebView2 与菜单重叠

**问题**: WebView2 控件和菜单栏直接添加到 Form.Controls 时会出现重叠。

**解决方案**: 使用 `TableLayoutPanel` 分离菜单和内容区域。

```csharp
// 错误写法
Controls.Add(webView);
Controls.Add(statusPanel);
Controls.Add(mainMenu);

// 正确写法 - 使用布局容器
var rootLayout = new TableLayoutPanel();
rootLayout.Controls.Add(mainMenu, 0, 0);      // 菜单在第一行
rootLayout.Controls.Add(contentPanel, 0, 1);   // 内容在第二行

var contentPanel = new Panel();
contentPanel.Controls.Add(webView);
contentPanel.Controls.Add(statusPanel);

Controls.Add(rootLayout);
```

### 3.4 WinForms STA 线程要求

**问题**: WebView2 和 WinForms 控件需要在 STA (Single-Threaded Apartment) 线程上运行。

**解决方案**: 确保 `[STAThread]` 属性标记在 `Main` 方法上，而不是其他方法。

```csharp
// 错误写法 - [STAThread] 放错了位置
[STAThread]
public static ApplicationStartupMode SelectStartupMode(string[] args)
{
    // ...
}

static int Main(string[] args)  // 缺少 [STAThread]
{
    // ...
}

// 正确写法
public static ApplicationStartupMode SelectStartupMode(string[] args)
{
    // ...
}

[STAThread]  // 必须在 Main 方法上
static int Main(string[] args)
{
    // ...
}
```

---

## 4. Python 路径解析问题

### 4.1 Worktree 中找不到 Python 虚拟环境

**问题**: 在 git worktree 中构建时，`.venv` 目录位于主仓库，worktree 中不存在。

**解决方案**: 检测 worktree 环境并解析主仓库路径。

```powershell
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    # Worktree: try the main repo's venv
    $mainRepoRoot = (git -C $RepoRoot rev-parse --path-format=absolute --git-common-dir 2>$null)
    if ($mainRepoRoot) {
        $mainRepoRoot = Split-Path $mainRepoRoot -Parent
        $mainPython = Join-Path $mainRepoRoot ".venv\Scripts\python.exe"
        if (Test-Path $mainPython -PathType Leaf) {
            $Python = $mainPython
            Write-Host "  Using main repo Python: $Python"
        }
    }
}
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python venv not found. Create a .venv in the repo root or set up a symlink."
}
```

### 4.2 运行时缺少 Python 依赖

**问题**: 安装后运行时找不到 Python 包，因为 `PYTHONPATH` 只配置了可选的 site-packages。

**解决方案**: 确保 `PYTHONPATH` 包含所有必要的路径。

```csharp
// 错误写法
environment["PYTHONPATH"] = layout.OptionalSitePackages;

// 正确写法
private static string BuildPythonPath(RuntimeLayout layout)
{
    return string.Join(
        Path.PathSeparator,
        new[]
        {
            layout.OptionalSitePackages,
            Path.Combine(layout.InstallRoot, "runtime", "site-packages"),
        });
}
```

---

## 5. 音频处理问题

### 5.1 Whisper 找不到 ffmpeg

**问题**: `whisper.audio.load_audio` 依赖 PATH 上的 `ffmpeg` 命令，但在 Windows 上 imageio-ffmpeg 安装的 ffmpeg 文件名可能是带版本号的（如 `ffmpeg-win-x86_64-v7.1.exe`），无法通过 `ffmpeg` 名称找到。

**解决方案**: 绕过 `whisper.audio.load_audio`，直接使用完整路径调用 ffmpeg 解码音频。

```python
# 错误写法 - 依赖 PATH 上的 ffmpeg
def transcribe_audio(path, whisper_available):
    model = whisper.load_model("base")
    result = model.transcribe(str(path), fp16=False)  # 内部调用 load_audio，依赖 ffmpeg

# 正确写法 - 直接用 ffmpeg 解码
def _decode_audio_to_pcm_array(path, ffmpeg_path):
    cmd = [
        ffmpeg_path,  # 使用完整路径
        "-nostdin", "-threads", "0",
        "-i", str(path),
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", "16000",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    pcm = np.frombuffer(result.stdout, dtype=np.int16).flatten()
    return pcm.astype(np.float32) / 32768.0

def transcribe_audio(path, whisper_available, ffmpeg_path):
    model = whisper.load_model("base")
    audio = _decode_audio_to_pcm_array(path, ffmpeg_path)
    result = model.transcribe(audio, fp16=False)  # 传入 numpy 数组而非文件路径
```

---

## 6. MinerU 解析问题

### 6.1 PDF 解析后端未指定

**问题**: MinerU 解析 PDF 时如果未指定后端，可能使用默认的 VLM 后端，导致在没有 GPU 的环境下失败。

**解决方案**: 对 PDF 文件显式指定 `-b pipeline` 后端。

```python
# 错误写法
cmd = ["mineru", "-o", str(output_dir), "-p", str(source_path)]
if source_path.suffix.lower() in MINERU_IMAGE_EXTENSIONS:
    cmd.extend(["-m", "ocr", "-b", "pipeline"])

# 正确写法
cmd = ["mineru", "-o", str(output_dir), "-p", str(source_path)]
if source_path.suffix.lower() in MINERU_IMAGE_EXTENSIONS:
    cmd.extend(["-m", "ocr", "-b", "pipeline"])
else:
    cmd.extend(["-b", "pipeline"])  # PDF 也要指定 pipeline 后端
```

---

## 7. 其他常见问题

### 7.1 Authenticode 签名验证模块缺失

**问题**: `Get-AuthenticodeSignature` cmdlet 在某些 PowerShell 环境中可能不可用。

**解决方案**: 添加模块导入并优雅处理缺失情况。

```powershell
Import-Module -Name Microsoft.PowerShell.Security -ErrorAction SilentlyContinue
$signature = Get-AuthenticodeSignature -FilePath $InstallerPath
```

### 7.2 SHA-256 哈希计算失败

**问题**: `Get-FileHash` 在某些环境下不可用（如 Server Core）。

**解决方案**: 使用 `certutil` 作为备选方案。

```powershell
# 优先使用 Get-FileHash
try {
    $hash = (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash
} catch {
    # 备选方案：使用 certutil
    $hash = ((certutil -hashfile $FilePath SHA256 | Select-Object -Index 1).Trim() -replace '\s+', '')
}
```

### 7.3 Inno Setup 路径问题

**问题**: Inno Setup 可能安装在非标准路径（如 E: 盘），导致构建脚本找不到编译器。

**解决方案**: 在构建脚本中添加多个可能的路径。

```powershell
$InnoSetupPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "E:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "E:\Inno Setup 6\ISCC.exe"
)

$ISCC = $InnoSetupPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ISCC) {
    throw "Inno Setup 6 not found. Install from https://jrsoftware.org/isinfo.php"
}
```

### 7.4 UTF-8 BOM 问题

**问题**: 某些文件（如 WebView2 manifest）可能包含 UTF-8 BOM，导致解析失败。

**解决方案**: 在读取文件时处理 BOM。

```python
# 读取时自动处理 BOM
with open(file_path, 'r', encoding='utf-8-sig') as f:
    content = f.read()
```

---

## 快速检查清单

构建安装包前，确认以下事项：

- [ ] Inno Setup 6 已安装且路径正确
- [ ] Python 虚拟环境存在且包含所有依赖
- [ ] WebView2 运行时安装包已下载（> 10MB）
- [ ] 构建脚本使用 `Out-File` 而非 `Set-Content`
- [ ] Pascal 脚本不使用 ADODB.Stream、CoCreateGuid、WMI
- [ ] WebView2 控件在初始化前设置为可见
- [ ] [STAThread] 属性标记在 Main 方法上
- [ ] PYTHONPATH 包含所有必要的 site-packages 路径
- [ ] ffmpeg 使用完整路径而非依赖 PATH
- [ ] MinerU PDF 解析指定 `-b pipeline` 后端

---

## 调试技巧

### 查看构建日志

```powershell
# 启用详细输出
$VerbosePreference = "Continue"
.\packaging\build_installer.ps1 -Verbose
```

### 测试安装包

```powershell
# 静默安装测试
.\output\TestSystem-Setup.exe /SILENT /LOG="install-test.log"

# 查看安装日志
Get-Content install-test.log
```

### 检查运行时环境

```powershell
# 验证 Python 环境
& "C:\Program Files\Test-System\runtime\python\python.exe" -c "import sys; print(sys.path)"

# 验证 WebView2
Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEE-13A6279B0078}" -ErrorAction SilentlyContinue
```

---

*文档版本: 2026-06-25*
*基于实际构建经验整理*
