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

便携包位于 `dist-portable/Test-System-Portable/`。

## 注意事项

- 首次使用需要配置 MiniMax 和 SiliconFlow API Key
- 打开 http://localhost:8002 进入模型设置页面
- 便携包包含 .venv 虚拟环境，无需额外安装依赖
