#!/usr/bin/env bash
#
# One-command local launcher for the Adaline Lead-Gen Engine.
#
#   ./run.sh           start everything (seeds demo data on first run)
#   ./run.sh --demo    re-seed the demo leads, then start
#   ./run.sh --fresh   wipe the database, re-seed, then start
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
  echo "→ Wiping database…"
  uv run python -m backend.scripts.reset_db
  rm -f data/.seeded
fi

echo "→ Setting up database + team accounts…"
uv run python -m backend.scripts.seed_users

if [ "$1" = "--demo" ] || [ "$1" = "--fresh" ] || [ ! -f data/.seeded ]; then
  echo "→ Adding demo leads…"
  uv run python -m backend.scripts.seed_leads
  touch data/.seeded
fi

echo "→ Starting servers…"
uv run uvicorn backend.app:app --port 8000 --reload &
BACK=$!
python3 -m http.server 5173 --directory frontend >/dev/null 2>&1 &
FRONT=$!
trap "echo; echo '→ Stopping…'; kill $BACK $FRONT 2>/dev/null" EXIT INT TERM

sleep 2
URL="http://localhost:5173/login.html"
echo ""
echo "  ✅  Adaline Lead-Gen Engine is running"
echo "      App:       $URL"
echo "      API docs:  http://localhost:8000/docs"
echo "      Login:     aslam  /  change_me_first_login"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo ""

# Best-effort: open the browser automatically.
(command -v open >/dev/null 2>&1 && open "$URL") \
  || (command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL") \
  || true

wait
