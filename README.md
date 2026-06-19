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

# 4. Seed the team's user accounts
uv run python -m backend.scripts.seed_users

# 5. Run the backend
uv run uvicorn backend.app:app --reload --port 8000
#    API docs:   http://localhost:8000/docs

# 6. Serve the frontend (separate terminal) — available from Phase 3 onward
python -m http.server 5173 --directory frontend
```

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

Phased build (see `CLAUDE.md` §11). **Phase 1 (backend skeleton + auth)
complete.** Phases 2–5 (leads CRUD, frontend, reports, scraper+scorer) follow.
