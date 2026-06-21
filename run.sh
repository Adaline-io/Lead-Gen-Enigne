#!/usr/bin/env bash
#
# One-command local launcher for the Adaline Lead-Gen Engine.
#
#   ./run.sh           start everything (clean — no demo leads)
#   ./run.sh --demo    also add ~27 demo leads to explore the UI
#   ./run.sh --fresh   wipe the database for a clean slate, then start
#
# Open http://localhost:5173/login.html and log in as  aslam / change_me_first_login
#
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "✗ 'uv' is not installed. Install it with:"
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh   (macOS/Linux)"
  echo "    irm https://astral.sh/uv/install.ps1 | iex        (Windows PowerShell)"
  exit 1
fi

echo "→ Installing dependencies (first run can take a minute)…"
uv sync --quiet

[ -f .env ] || { cp .env.example .env; echo "→ Created .env from .env.example"; }

if [ "$1" = "--fresh" ]; then
  echo "→ Wiping database for a clean slate…"
  uv run python -m backend.scripts.reset_db
fi

echo "→ Setting up database + team accounts…"
uv run python -m backend.scripts.seed_users

if [ "$1" = "--demo" ]; then
  echo "→ Adding demo leads…"
  uv run python -m backend.scripts.seed_leads
fi

echo "→ Starting the app (single process)…"
URL="http://localhost:8000/"
echo ""
echo "  ✅  Adaline Lead-Gen Engine is starting"
echo "      App:       $URL"
echo "      API docs:  http://localhost:8000/docs"
echo "      Login:     aslam  /  change_me_first_login"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# Best-effort: open the browser shortly after the server boots.
( sleep 2
  (command -v open >/dev/null 2>&1 && open "$URL") \
    || (command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL") \
    || true ) &

# Run the single server in the foreground (serves API + frontend). Ctrl+C stops it.
exec uv run uvicorn backend.app:app --port 8000 --reload
