# Test-System Windows 便携包

## 构建

构建机需要安装 `uv`。脚本会自动获取精确版本的 CPython 3.13.10：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

产物：

```text
dist-portable/Test-System-Portable/
dist-portable/Test-System-Portable.zip
```

仅生成未压缩目录：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1 -NoArchive
```

可显式指定构建机工具路径：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1 `
  -FfmpegBin "D:\tools\ffmpeg\bin" `
  -LibreOfficePath "C:\Program Files\LibreOffice\program\soffice.exe"
```

## 包含内容

- 独立 CPython 3.13.10 运行时；
- 两个服务的基础 Python 依赖；
- 项目源码和双击启动器；
- 构建机可用时附带 ffmpeg；
- 构建机可用时附带 LibreOffice。

便携包不会复制开发环境 `.venv`，也不依赖目标电脑安装 Python、pip 或 uv。

## MinerU

压缩包不包含 MinerU 依赖和模型。

用户首次双击 `start_services.bat` 时，启动器会检查 MinerU：

- 选择安装：使用包内 Python 联网安装固定版本 `mineru[core]==3.3.1`；
- 暂不安装：两个服务继续启动，文本、Office 和文本型 PDF 使用基础解析；
- 首次解析扫描 PDF 或图片时，MinerU 自动下载模型；
- 模型缓存保存在 `runtime/models/mineru/`，不会写入系统 Python 目录。

也可以双击 `install_mineru.bat` 重新安装。

## 数据与密钥

- `.env` 由 `.env.example` 生成，不携带构建机真实密钥；
- 不包含知识库、会话和生成产物；
- 新安装环境从空知识库列表开始；
- 用户需要在前端「模型设置」中填写 LLM、Embedding 和 Rerank API Key。

## 日志

```text
runtime/logs/bootstrap.log
runtime/logs/runtime-check.json
runtime/logs/mineru-install.log
```

## Windows 安装包

构建 Windows 原生安装包（相比便携包增加 WebView2 桌面宿主和 Inno Setup 安装器）：

### 获取 WebView2 运行时前提条件

```powershell
powershell -ExecutionPolicy Bypass -File packaging\prerequisites.ps1
```

离线模式（仅验证已缓存文件）：
```powershell
powershell -ExecutionPolicy Bypass -File packaging\prerequisites.ps1 -Offline
```

### 一键构建安装包

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
```

产物：
```text
dist-installer\Test-System-Setup-<版本>-x64.exe
dist-installer\Test-System-Setup-<版本>-x64.exe.sha256
dist-installer\build-manifest.json
```

### 构建选项

跳过测试（仅本地诊断，正式发布不得跳过）：
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 -SkipTests
```

指定自定义路径或代码签名：
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1 `
  -PythonHome "C:\cpython-3.13.10" `
  -FfmpegBin "D:\tools\ffmpeg\bin" `
  -LibreOfficePath "C:\Program Files\LibreOffice\program\soffice.exe" `
  -CertificateThumbprint "YOUR_THUMBPRINT"
```

详细发布流程见 [docs/releasing-windows.md](../docs/releasing-windows.md)。
