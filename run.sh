#!/usr/bin/env bash
#
# One-command local launcher for the Adaline Lead-Gen Engine.
#
#   ./run.sh           start everything (clean — no demo leads)
#   ./run.sh --demo    also add ~27 demo leads to explore the UI
#   ./run.sh --fresh   wipe the database for a clean slate, then start
#
# Open http://localhost:5173/login.html and log in as  aslam / admin
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

# Confirm gosom is wired up. The app launches gosom itself on every Find Leads
# search (as a subprocess) — you do NOT run gosom separately. This just checks
# the binary is reachable so you find out at startup, not mid-search.
GOSOM_BIN="$(grep -E '^[[:space:]]*GOSOM_BIN=' .env 2>/dev/null | tail -1 | sed -E 's/^[^=]*=//; s/^["'"'"']//; s/["'"'"']$//')"
[ -n "$GOSOM_BIN" ] || GOSOM_BIN="/usr/local/bin/google-maps-scraper"
if [ -x "$GOSOM_BIN" ] && [ ! -d "$GOSOM_BIN" ]; then
  echo "→ gosom found: $GOSOM_BIN  (live Google Maps scraping enabled)"
elif [ -d "$GOSOM_BIN" ]; then
  echo "⚠ GOSOM_BIN points to a folder, not the binary: $GOSOM_BIN"
  echo "    Build it once:  (cd \"$GOSOM_BIN\" && go build -o google-maps-scraper .)"
  echo "    Then in .env:   GOSOM_BIN=$GOSOM_BIN/google-maps-scraper"
elif [ -e "$GOSOM_BIN" ]; then
  echo "⚠ gosom at $GOSOM_BIN is not executable — run:  chmod +x \"$GOSOM_BIN\""
else
  echo "⚠ gosom NOT found at: $GOSOM_BIN"
  echo "    Find Leads will fail until GOSOM_BIN in .env points to the binary (see README)."
fi

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
echo "      Login:     aslam  /  admin"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# Best-effort: open the browser shortly after the server boots.
( sleep 2
  (command -v open >/dev/null 2>&1 && open "$URL") \
    || (command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL") \
    || true ) &

# Run the single server in the foreground (serves API + frontend). Ctrl+C stops it.
# No --reload: the scraper runs in a background task, and a reload mid-scrape
# would kill it and leave the job stuck on "running". Restart manually to pick
# up code changes.
exec uv run uvicorn backend.app:app --port 8000
