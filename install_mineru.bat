@echo off
setlocal EnableExtensions
%SystemRoot%\System32\chcp.com 65001 >nul 2>&1

set "ROOT=%~dp0"
set "PYTHON=%ROOT%runtime\python\python.exe"
set "RUNTIME_MANAGER=%ROOT%packaging\portable_runtime.py"

if not exist "%PYTHON%" (
    echo [错误] 找不到包内 Python：%PYTHON%
    pause
    exit /b 1
)

"%PYTHON%" "%RUNTIME_MANAGER%" install-mineru --root "%ROOT%."
if errorlevel 1 (
    echo.
    echo 安装失败。请查看 runtime\logs\mineru-install.log
) else (
    echo.
    echo MinerU 安装完成。
)
pause
exit /b %ERRORLEVEL%
