@echo off
chcp 65001 >/dev/null
echo ==================================================
echo   AI话术陪练系统 - 启动脚本
echo ==================================================
echo.
echo 正在启动AI陪练服务 (端口8002)...
echo.
echo 前端界面：请双击 static/index.html
echo 或在浏览器中打开：file:///%~dp0static/index.html
echo.
python tutor_backend.py
pause
