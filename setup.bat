@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo ERROR: uv is not installed or is not on PATH.
  echo Install uv from https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
uv sync
if errorlevel 1 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul
echo.
echo Setup complete. Open .env and add your Telegram and OpenRouter keys.
echo Then run run.bat.
pause
