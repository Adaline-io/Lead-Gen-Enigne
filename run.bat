@echo off
REM One-command local launcher for the Adaline Lead-Gen Engine (Windows).
REM Open http://localhost:5173/login.html  (login: aslam / admin)
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
  echo 'uv' is not installed. Install it with:
  echo     irm https://astral.sh/uv/install.ps1 ^| iex
  exit /b 1
)

echo Installing dependencies (first run can take a minute)...
uv sync

if not exist .env copy .env.example .env >nul

echo Setting up database + team accounts...
uv run python -m backend.scripts.seed_users

if "%1"=="--demo" (
  echo Adding demo leads...
  uv run python -m backend.scripts.seed_leads
)

echo Starting the app (single process)...
echo.
echo   Adaline Lead-Gen Engine
echo       App:       http://localhost:8000/
echo       API docs:  http://localhost:8000/docs
echo       Login:     aslam  /  admin
echo.
echo   Press Ctrl+C in this window to stop.

REM open the browser shortly after, then run the single server in foreground
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000/"
uv run uvicorn backend.app:app --port 8000 --reload
