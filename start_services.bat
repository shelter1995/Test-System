@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "VENV_SCRIPTS=%VENV%\Scripts"
set "PYTHON=%VENV_SCRIPTS%\python.exe"
set "ACTIVATE=%VENV_SCRIPTS%\activate.bat"
set "RAG_DIR=%ROOT%rag-anything-api"
set "TUTOR_DIR=%ROOT%ai-tutor-system"
set "RAG_HEALTH=http://localhost:8003/health"
set "TUTOR_STATUS=http://localhost:8002/api/status"
set "APP_URL=http://localhost:8002"
set "OPEN_BROWSER=1"
set "PAUSE_AT_END=1"

if /I "%~1"=="rag" goto run_rag
if /I "%~1"=="tutor" goto run_tutor
call :parse_args %*

echo ==================================================
echo   Test-System launcher
echo ==================================================
echo.
echo Model settings:
echo   Open http://localhost:8002 and choose Model Settings to edit inference, embedding, and rerank models.
echo.

if not exist "%PYTHON%" (
    echo [ERROR] Python was not found at:
    echo         %PYTHON%
    echo.
    echo Run setup first, or recreate the virtual environment.
    pause
    exit /b 1
)

if not exist "%ACTIVATE%" (
    echo [ERROR] Virtual environment activation script was not found:
    echo         %ACTIVATE%
    pause
    exit /b 1
)

echo Checking service ports...
call :check_url "%RAG_HEALTH%"
if errorlevel 1 (
    echo Starting RAG service on port 8003...
    start "Test-System RAG 8003" "%ComSpec%" /k ""%~f0" rag"
) else (
    echo RAG service is already running.
)

call :check_url "%TUTOR_STATUS%"
if errorlevel 1 (
    echo Starting Tutor service on port 8002...
    start "Test-System Tutor 8002" "%ComSpec%" /k ""%~f0" tutor"
) else (
    echo Tutor service is already running.
)

echo.
echo Both service windows have been requested. Waiting for readiness...

call :wait_url "%RAG_HEALTH%" "RAG service" 120
if errorlevel 1 (
    echo.
    echo [ERROR] RAG service did not become ready.
    pause
    exit /b 1
)

call :wait_url "%TUTOR_STATUS%" "Tutor service" 120
if errorlevel 1 (
    echo.
    echo [ERROR] Tutor service did not become ready.
    pause
    exit /b 1
)

echo.
echo Services are ready.
if "%OPEN_BROWSER%"=="1" (
    echo Opening %APP_URL%
    start "" "%APP_URL%"
) else (
    echo Browser launch skipped.
)
echo.
echo You can close this launcher window. Service windows must stay open.
if "%PAUSE_AT_END%"=="1" pause
exit /b 0

:run_rag
set "PATH=%VENV_SCRIPTS%;%PATH%"
cd /d "%RAG_DIR%"
call "%ACTIVATE%"
python start.py
pause
exit /b %ERRORLEVEL%

:run_tutor
set "PATH=%VENV_SCRIPTS%;%PATH%"
cd /d "%TUTOR_DIR%"
call "%ACTIVATE%"
python tutor_backend.py
pause
exit /b %ERRORLEVEL%

:check_url
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%~1' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
exit /b %ERRORLEVEL%

:wait_url
set "WAIT_URL=%~1"
set "WAIT_NAME=%~2"
set "WAIT_MAX=%~3"
echo Waiting for %WAIT_NAME%...
for /L %%I in (1,1,%WAIT_MAX%) do (
    call :check_url "%WAIT_URL%"
    if not errorlevel 1 (
        echo %WAIT_NAME% is ready.
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
echo Timeout waiting for %WAIT_NAME% at %WAIT_URL%
exit /b 1

:parse_args
if "%~1"=="" exit /b 0
if /I "%~1"=="--no-browser" set "OPEN_BROWSER=0"
if /I "%~1"=="--no-pause" set "PAUSE_AT_END=0"
shift
goto parse_args
