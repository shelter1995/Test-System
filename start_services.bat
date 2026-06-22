@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "PORTABLE_PYTHON=%ROOT%runtime\python\python.exe"
set "DEV_PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PYTHON=%PORTABLE_PYTHON%"
set "RUNTIME_MODE=portable"
if not exist "%PYTHON%" if exist "%DEV_PYTHON%" (
    set "PYTHON=%DEV_PYTHON%"
    set "RUNTIME_MODE=development"
)
set "RUNTIME_MANAGER=%ROOT%packaging\portable_runtime.py"
set "RUNTIME_LOGS=%ROOT%runtime\logs"
set "RUNTIME_STATUS=%RUNTIME_LOGS%\runtime-check.json"
set "RUNTIME_VARS=%RUNTIME_LOGS%\runtime-check.cmd"
set "RAG_DIR=%ROOT%rag-anything-api"
set "TUTOR_DIR=%ROOT%ai-tutor-system"
set "RAG_HEALTH=http://localhost:8003/health"
set "TUTOR_STATUS=http://localhost:8002/api/status"
set "APP_URL=http://localhost:8002"
set "OPEN_BROWSER=1"
set "PAUSE_AT_END=1"

call :configure_runtime

if /I "%~1"=="rag" goto run_rag
if /I "%~1"=="tutor" goto run_tutor
call :parse_args %*

echo ==================================================
echo   Test-System 启动器
echo ==================================================
echo.

if not exist "%PYTHON%" (
    echo [错误] 未找到可用的 Python：
    echo        便携运行时：%PORTABLE_PYTHON%
    echo        开发虚拟环境：%DEV_PYTHON%
    echo 便携包请重新解压完整压缩包；源码仓库请先创建 .venv 并安装依赖。
    pause
    exit /b 1
)

if not exist "%RUNTIME_MANAGER%" (
    echo [错误] 运行时检查器不存在：
    echo        %RUNTIME_MANAGER%
    pause
    exit /b 1
)

if /I "%RUNTIME_MODE%"=="development" goto runtime_ready

if not exist "%RUNTIME_LOGS%" mkdir "%RUNTIME_LOGS%"
"%PYTHON%" "%RUNTIME_MANAGER%" check --root "%ROOT%." --json-output "%RUNTIME_STATUS%" --cmd-output "%RUNTIME_VARS%" >nul
if errorlevel 1 (
    echo [错误] 无法完成运行时检查。详情：
    type "%RUNTIME_STATUS%"
    pause
    exit /b 1
)

call "%RUNTIME_VARS%"
if not "%BASE_READY%"=="1" (
    echo [错误] 基础运行依赖不完整，服务无法启动。
    echo 缺少模块: %MISSING_BASE_MODULES%
    echo 检查日志：%RUNTIME_STATUS%
    pause
    exit /b 1
)

if not "%MINERU_READY%"=="1" (
    echo 检测到复杂文档智能解析组件 MinerU 尚未安装。
    echo 安装后可处理扫描 PDF、图片和复杂排版文档。
    echo 安装需要联网，并会占用较多磁盘空间。
    echo.
    choice /C YN /N /M "是否立即安装 MinerU？[Y/N] "
    if errorlevel 2 goto skip_mineru
    "%PYTHON%" "%RUNTIME_MANAGER%" install-mineru --root "%ROOT%."
    if errorlevel 1 (
        echo.
        echo [警告] MinerU 安装失败，系统将以基础解析模式启动。
        echo 日志：%RUNTIME_LOGS%\mineru-install.log
    ) else (
        echo MinerU 安装完成。
    )
)

:skip_mineru
:runtime_ready
echo.
echo 正在检查服务端口...
call :check_url "%RAG_HEALTH%"
if errorlevel 1 (
    echo 正在启动 RAG 服务（8003）...
    start "Test-System RAG 8003" "%ComSpec%" /k ""%~f0" rag"
) else (
    echo RAG 服务已经运行。
)

call :check_url "%TUTOR_STATUS%"
if errorlevel 1 (
    echo 正在启动 AI 陪练服务（8002）...
    start "Test-System Tutor 8002" "%ComSpec%" /k ""%~f0" tutor"
) else (
    echo AI 陪练服务已经运行。
)

echo.
echo 正在等待服务就绪...
call :wait_url "%RAG_HEALTH%" "RAG 服务" 120
if errorlevel 1 (
    echo [错误] RAG 服务未能在规定时间内启动。
    pause
    exit /b 1
)

call :wait_url "%TUTOR_STATUS%" "AI 陪练服务" 120
if errorlevel 1 (
    echo [错误] AI 陪练服务未能在规定时间内启动。
    pause
    exit /b 1
)

echo.
echo 服务已就绪。
if "%OPEN_BROWSER%"=="1" start "" "%APP_URL%"
if "%PAUSE_AT_END%"=="1" pause
exit /b 0

:run_rag
call :configure_runtime
cd /d "%RAG_DIR%"
"%PYTHON%" start.py
pause
exit /b %ERRORLEVEL%

:run_tutor
call :configure_runtime
cd /d "%TUTOR_DIR%"
"%PYTHON%" tutor_backend.py
pause
exit /b %ERRORLEVEL%

:configure_runtime
set "PYTHONUTF8=1"
if /I "%RUNTIME_MODE%"=="development" goto configure_development_runtime
set "PYTHONPATH=%ROOT%runtime\optional-site-packages;%ROOT%runtime\site-packages;%ROOT%rag-anything-api"
set "HF_HOME=%ROOT%runtime\models\mineru\huggingface"
set "HUGGINGFACE_HUB_CACHE=%ROOT%runtime\models\mineru\huggingface\hub"
set "MODELSCOPE_CACHE=%ROOT%runtime\models\mineru\modelscope"
set "MINERU_TOOLS_CONFIG_JSON=%ROOT%runtime\models\mineru\mineru.json"
set "MINERU_PYTHON=%PYTHON%"
set "PATH=%ROOT%runtime\python;%ROOT%runtime\tools\ffmpeg\bin;%ROOT%runtime\tools\LibreOffice\program;%PATH%"
if exist "%ROOT%runtime\tools\LibreOffice\program\soffice.exe" set "LIBREOFFICE_PATH=%ROOT%runtime\tools\LibreOffice\program\soffice.exe"
exit /b 0

:configure_development_runtime
set "PYTHONPATH=%ROOT%rag-anything-api;%PYTHONPATH%"
set "MINERU_PYTHON=%PYTHON%"
set "PATH=%ROOT%.venv\Scripts;%PATH%"
exit /b 0

:check_url
"%PYTHON%" "%RUNTIME_MANAGER%" check-url "%~1" --timeout 2 >nul 2>nul
exit /b %ERRORLEVEL%

:wait_url
set "WAIT_URL=%~1"
set "WAIT_NAME=%~2"
set "WAIT_MAX=%~3"
for /L %%I in (1,1,%WAIT_MAX%) do (
    call :check_url "%WAIT_URL%"
    if not errorlevel 1 (
        echo %WAIT_NAME% 已就绪。
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
exit /b 1

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"
if /I "%~1"=="--no-pause" set "PAUSE_AT_END=0"
shift
goto parse_args
