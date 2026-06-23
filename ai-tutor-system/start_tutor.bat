@echo off
%SystemRoot%\System32\chcp.com 65001 >nul 2>&1
setlocal EnableExtensions

set "TUTOR_DIR=%~dp0"
set "ROOT=%TUTOR_DIR%.."
set "VENV=%ROOT%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "ACTIVATE=%VENV%\Scripts\activate.bat"

echo ==================================================
echo   AI话术陪练系统 - 启动脚本
echo ==================================================
echo.

if exist "%ACTIVATE%" (
    call "%ACTIVATE%"
)

if exist "%PYTHON%" (
    set "PYTHON_CMD=%PYTHON%"
) else (
    set "PYTHON_CMD=python"
)

echo 正在启动AI陪练服务 (端口8002)...
echo.
echo 前端界面：http://localhost:8002
echo.
cd /d "%TUTOR_DIR%"
"%PYTHON_CMD%" tutor_backend.py
pause
