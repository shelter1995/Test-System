# Test-System 打包与分发

## 桌面快捷方式

运行以下命令在桌面创建快捷方式：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\create_shortcut.ps1
```

## 便携包

运行以下命令生成便携包：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\package_windows.ps1
```

便携包位于 `dist-portable/Test-System-Portable.zip`。

### 便携包说明

- 这是一个 Windows 本地运行包
- 包含两个本地服务，启动后打开 http://localhost:8002
- 用户仍需配置有效的 MiniMax 和 SiliconFlow API Key
- 首版支持便携文件夹/zip，不支持云端部署
