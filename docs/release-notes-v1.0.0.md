## 智学工作台 v1.0.0

首个 Windows 桌面安装包正式发布。基于 WebView2 嵌入前端，内置 Tutor + RAG 双服务，一键安装即用。

### ✨ 主要功能

- **桌面端体验**：原生 WinForms 应用，自动启动后端服务
- **WebView2 内嵌**：无需打开浏览器，应用启动即用
- **数据隔离**：程序文件与用户数据分离，升级不丢失数据
- **单实例**：避免端口冲突，关闭窗口自动释放资源
- **可选 MinerU**：安装时可选增强解析组件（PDF OCR、音视频转写）

### 📦 安装包

| 文件 | 说明 |
|------|------|
| `智学工作台-Setup-1.0.0-x64.exe` | Windows 10/11 x64 离线安装包（约 290 MB）|
| `智学工作台-Setup-1.0.0-x64.exe.sha256` | SHA-256 校验文件 |
| `build-manifest.json` | 构建元数据（commit hash、依赖版本）|

### 🚀 快速开始

1. 下载 `智学工作台-Setup-1.0.0-x64.exe`
2. 双击安装（建议安装在非系统盘）
3. 启动「智学工作台」桌面图标
4. 在「模型设置」中配置 API Key

**系统要求**：Windows 10 1809+ / Windows 11 x64

### 🔧 校验完整性

```powershell
# PowerShell
Get-FileHash .\智学工作台-Setup-1.0.0-x64.exe -Algorithm SHA256
# 与 .sha256 文件对比

# 或使用 certutil
certutil -hashfile 智学工作台-Setup-1.0.0-x64.exe SHA256
```

### 📝 完整更新日志

<details>
<summary>点击展开</summary>

#### Windows 桌面安装包

- 建立产品版本合约 (`version.json`, `packaging/product_version.py`)
- 实现运行时路径分离：通过 `TEST_SYSTEM_*` 环境变量将数据目录与程序文件分离
- 为两个服务添加认证的 localhost 关闭端点 (`/__desktop/shutdown`)
- 创建 Windows 安装镜像构建器 (`packaging/installer_builder.py`)
- 搭建 .NET 8 WinForms 桌面宿主，使用 WebView2 嵌入前端
- 实现后端进程生命周期管理：Windows Job Object 确保进程随桌面宿主退出
- 添加启动协调、单实例激活和健康探测
- 实现 WebView2 安全导航策略和文件保存下载协调
- 构建可选的 MinerU 增强解析组件安装管理器
- 创建 Inno Setup 安装脚本，支持自定义数据目录和保留数据的卸载
- 实现安全的用户数据删除守卫
- 添加 WebView2 前提条件获取脚本和签名验证
- 构建一键发布流水线 (`packaging/build_installer.ps1`)
- 实现安装包产物的自动审计 (`packaging/verify_installer_artifact.py`)

</details>

### ⚠️ 已知问题

- 首次启动 WebView2 初始化可能需要 5-10 秒
- 若安装路径包含中文，安装时请使用默认路径

### 🙏 反馈

遇到问题请在 [Issues](https://github.com/shelter1995/Test-System/issues) 提交。