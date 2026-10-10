@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
  echo ERROR: .env was not found. Run setup.bat first.
  pause
  exit /b 1
)
uv run python main.py
if errorlevel 1 (
  echo.
  echo The bot stopped with an error. Read the message above.
  pause
)
