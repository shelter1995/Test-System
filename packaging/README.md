# Test-System 打包与分发

## 桌面快捷方式

运行以下命令在桌面创建快捷方式：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\create_shortcut.ps1
```

快捷方式会调用项目根目录的 `start_services.bat`，自动启动 RAG API 和统一工作台，并打开 http://localhost:8002。

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
- 默认使用传统 RAG 快速处理 `.txt`、`.md`、`.csv`、`.pdf`、`.docx`、`.xlsx`
- RAG-Anything 高级解析仍需要 MinerU 等本地依赖正常可用
- 支持便携文件夹/zip，不包含云端部署配置
