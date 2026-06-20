@echo off
REM One-command local launcher for the Adaline Lead-Gen Engine (Windows).
REM Open http://localhost:5173/login.html  (login: aslam / change_me_first_login)
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

if not exist data\.seeded (
  echo Adding demo leads...
  uv run python -m backend.scripts.seed_leads
  type nul > data\.seeded
)

echo Starting servers...
start "Adaline backend"  cmd /c "uv run uvicorn backend.app:app --port 8000 --reload"
start "Adaline frontend" cmd /c "python -m http.server 5173 --directory frontend"

timeout /t 3 >nul
start "" http://localhost:5173/login.html

echo.
echo   Adaline Lead-Gen Engine is running
echo       App:       http://localhost:5173/login.html
echo       API docs:  http://localhost:8000/docs
echo       Login:     aslam  /  change_me_first_login
echo.
echo   Close the two server windows to stop.
