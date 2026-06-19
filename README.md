# Adaline Lead-Gen Engine

Internal sales CRM for **Adaline** (Myadaline Communications LLP, Calicut). It
consumes leads from the [gosom Google Maps scraper](https://github.com/gosom/google-maps-scraper),
scores them for fit with Claude, and surfaces them to the sales team for
WhatsApp outreach and pipeline tracking. Built to replace ad-hoc spreadsheet
lead tracking for a 5–10 person team.

## Tech stack

Python 3.11 · FastAPI · SQLAlchemy 2.x + Alembic · SQLite · passlib[bcrypt] ·
Anthropic SDK, managed with [`uv`](https://docs.astral.sh/uv/). Frontend is
vanilla HTML/CSS/ES-module JavaScript (no build step). Auth is server-side
HMAC-signed cookie sessions. This is a **local-first MVP** — Docker/VPS
deployment is deferred.

> Built at the repo root (not a nested folder). Alembic owns the schema, but
> `seed_users` and app startup also run `create_all()` so first-run works
> without a manual migrate step.

## Local setup

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Generate a real SESSION_SECRET (>= 32 chars) and paste it into .env:
python -c "import secrets; print(secrets.token_urlsafe(48))"
# (If you skip this, `seed_users` will generate and write one for you.)

# 3. Create the database schema
uv run alembic upgrade head

# 4. Seed the team's user accounts (+ optional demo leads)
uv run python -m backend.scripts.seed_users
uv run python -m backend.scripts.seed_leads     # ~27 demo leads to explore the UI

# 5. Run the backend
uv run uvicorn backend.app:app --reload --port 8000
#    API docs:   http://localhost:8000/docs

# 6. Serve the frontend (separate terminal)
python -m http.server 5173 --directory frontend
#    Then open  http://localhost:5173/login.html
```

> Open the app via **http://localhost:5173/login.html** (served over HTTP) —
> not the `file://` path, or the browser will block the session cookie.
> The backend origin the frontend talks to is set by `API_BASE` in
> `frontend/js/api.js` (defaults to `http://localhost:8000`).

## First login

Seeded accounts (all share the same default password):

| Username  | Role   | Display name |
|-----------|--------|--------------|
| `jareer`  | admin  | Jareer       |
| `ibrahim` | admin  | Ibrahim      |
| `aslam`   | sales  | Aslam        |
| `shijas`  | sales  | Shijas       |
| `sales1`  | sales  | Sales Rep    |

**Default password:** `change_me_first_login` — **⚠ CHANGE THIS ON FIRST
LOGIN.** There is no password-reset flow in the MVP; an admin resets manually.

## Adding gosom (scraper) — Phase 5

1. Install the gosom scraper locally (see the link above).
2. Point `GOSOM_BIN` in `.env` at the binary
   (default `/usr/local/bin/google-maps-scraper`).
3. Trigger a search from the **Find Leads** view and watch the job run.

## Running tests

```bash
uv run pytest            # whole suite
uv run pytest backend/tests/test_auth.py -v
```

## Project structure

```
backend/
  app.py          FastAPI entry: middleware, error shape, routers
  config.py       Pydantic settings (.env)
  db.py           engine, session, get_db dependency
  models.py       SQLAlchemy models (users, leads, jobs, activity)
  schemas.py      Pydantic request/response schemas
  auth.py         hashing + current_user dependency
  routers/        auth (+ leads, jobs, reports in later phases)
  services/       scraper, scorer, whatsapp (Phase 5)
  prompts/        per-vertical Claude scoring prompts (Phase 5)
  scripts/        seed_users, reset_db
  tests/          pytest suites
alembic/          migrations
frontend/         vanilla JS app (Phase 3+)
reference/         design + build-doc + sample scraper output
```

## Where to make changes

- **Scoring prompts:** `backend/prompts/{vertical}.md`
- **WhatsApp message templates:** `backend/services/whatsapp.py`
- **Frontend design tokens:** `frontend/styles.css`
- **Environment / config:** `.env` (see `.env.example`)

## Build status

All five phases (see `CLAUDE.md` §11) are built:

1. ✅ Backend skeleton + session auth
2. ✅ Leads CRUD, filtering, bulk, approve/discard + demo seed
3. ✅ Vanilla-JS frontend (login, pipeline, lead detail panel, dark/light) matching the design reference
4. ✅ Reports — KPI cards, funnel, by-status / by-vertical bars, rep load
5. ✅ Scraper (gosom subprocess) + Claude scoring + WhatsApp links, with a background job + review queue

Backend test suite: `uv run pytest` (43 tests).

### To enable live scraping (Phase 5)

The **Find Leads** screen needs the gosom binary on the machine running the
backend. Without it, a started job fails with a clear "gosom binary not found"
message (everything else still works). To enable it:

1. Install gosom: https://github.com/gosom/google-maps-scraper
2. Set `GOSOM_BIN` in `.env` to the binary path.
3. Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`) so scored leads
   get a real score/reason — otherwise leads import unscored with a
   "scoring error: ANTHROPIC_API_KEY not configured" note.
