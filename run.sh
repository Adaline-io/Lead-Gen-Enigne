#!/usr/bin/env bash
#
# One-command local launcher for the Adaline Lead-Gen Engine.
#
#   ./run.sh           start everything (clean — no demo leads)
#   ./run.sh --demo    also add ~27 demo leads to explore the UI
#   ./run.sh --fresh   wipe the database for a clean slate, then start
#   ./run.sh --lan     serve to the whole network (team CRM mode) — prints the
#                      address teammates open from their own devices
#
# Open http://localhost:5173/login.html and log in as  aslam / admin
#
set -e
cd "$(dirname "$0")"

# Parse flags (any order). --lan binds to every network interface so other
# devices on the same Wi-Fi/LAN can reach this machine; default is localhost.
MODE_FRESH=0; MODE_DEMO=0; HOST="127.0.0.1"
for arg in "$@"; do
  case "$arg" in
    --fresh) MODE_FRESH=1 ;;
    --demo)  MODE_DEMO=1 ;;
    --lan)   HOST="0.0.0.0" ;;
  esac
done

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

if [ "$MODE_FRESH" = "1" ]; then
  echo "→ Wiping database for a clean slate…"
  uv run python -m backend.scripts.reset_db
fi

echo "→ Setting up database + team accounts…"
uv run python -m backend.scripts.seed_users

if [ "$MODE_DEMO" = "1" ]; then
  echo "→ Adding demo leads…"
  uv run python -m backend.scripts.seed_leads
fi

echo "→ Starting the app (single process)…"
echo ""
echo "  ✅  Adaline Lead-Gen Engine is starting"
if [ "$HOST" = "0.0.0.0" ]; then
  # Detect this machine's LAN IP so teammates know what to open.
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$LAN_IP" ] || LAN_IP="<this-machine-ip>"
  echo "      Team CRM mode — share this with the team:"
  echo "      App:       http://$LAN_IP:8000/"
  echo "      On THIS machine: http://localhost:8000/"
  echo "      Login:     aslam  /  admin   (everyone gets their own — see 👥 Team)"
else
  echo "      App:       http://localhost:8000/"
  echo "      API docs:  http://localhost:8000/docs"
  echo "      Login:     aslam  /  admin"
fi
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# Best-effort: open a browser on THIS machine (skip in --lan/server mode).
if [ "$HOST" != "0.0.0.0" ]; then
  ( sleep 2
    (command -v open >/dev/null 2>&1 && open "http://localhost:8000/") \
      || (command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:8000/") \
      || true ) &
fi

# Run the single server in the foreground (serves API + frontend). Ctrl+C stops it.
# No --reload: the scraper runs in a background task, and a reload mid-scrape
# would kill it and leave the job stuck on "running". Restart manually to pick
# up code changes.
exec uv run uvicorn backend.app:app --host "$HOST" --port 8000
