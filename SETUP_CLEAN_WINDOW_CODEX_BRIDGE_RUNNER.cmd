@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SETUP_CLEAN_WINDOW_CODEX_BRIDGE_RUNNER.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Setup did not complete. Exit code: %RC%.
  echo Leave this window open and send the message to ChatGPT.
) else (
  echo Setup completed successfully.
)
echo.
pause
exit /b %RC%
