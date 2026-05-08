@echo off
setlocal

cd /d "%~dp0"
echo [INFO] Start skill pipeline...
python run_skill_pipeline_once.py
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% neq 0 (
  echo [ERROR] Pipeline failed. Check training_output\_skill_pipeline_last_report.json
  exit /b %EXIT_CODE%
)

echo [OK] Pipeline passed.
echo [INFO] Report: training_output\_skill_pipeline_last_report.json
exit /b 0
