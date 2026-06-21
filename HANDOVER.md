# Adaline Lead-Gen Engine — Handover

Internal sales CRM: find businesses (Google Maps + LinkedIn), AI-score them for
fit, review/approve, and work them through a WhatsApp-driven pipeline. Local-first
MVP — one process, SQLite, no deploy infra required.

## Run it

```bash
uv sync
cp .env.example .env            # install gosom + set GOSOM_BIN (see README)
uv run python -m backend.scripts.seed_users
./run.sh                        # or: uv run uvicorn backend.app:app --port 8000
```
Open **http://localhost:8000/**. The backend serves the frontend (single process).
Logins (password `admin`, change on first login):
`jareer`/`ibrahim` (admin), `aslam`/`shijas`/`sales1` (sales).

`./run.sh --demo` seeds sample leads · `./run.sh --fresh` wipes & reseeds.

## Architecture

```
Browser (vanilla JS, hash router, tiny reactive store)
   │  same-origin fetch + cookie session
FastAPI (serves the frontend too)
   ├─ routers: auth · leads · jobs · reports
   ├─ services: quality (scoring) · expand (related industries) ·
   │            scraper (gosom) · linkedin (linkedin-api) · geocode · intake · whatsapp
   └─ SQLAlchemy 2.x → SQLite     scrapers run as BackgroundTasks
```
Migrations: `uv run alembic upgrade head` (also auto-created on first run).
Tests: `uv run pytest` (90).

## Roles
- **admin** — runs scrapes, approves/discards, assigns owners, imports CSV, sets targets.
- **sales** — works assigned leads (status, notes, contact, flag), manual add, export.
- **viewer** — read-only.

## Lead sources
- **Google Maps** via gosom binary (`GOSOM_BIN`). Real data only — if the binary
  is absent the scrape job fails with a clear "install gosom" error (no demo).
- **LinkedIn** via `linkedin-api` (industry/keyword company search). Account is
  baked in (see Secrets). Raises a clear error until configured (no demo). Safety:
  `LINKEDIN_DAILY_CAP`, throttle, and a Test-connection button.
- **Related-industry expansion** — a typed industry expands to distinct related
  categories (Claude if `ANTHROPIC_API_KEY` set, curated map otherwise), de-duped.

## Scoring
Deterministic engine (`services/quality.py`) scores every lead 0–10 from its own
fields; Claude refines when `ANTHROPIC_API_KEY` is set, falling back to the
data-driven score on any failure.

## Config & secrets
- `.env` (git-ignored) — see `.env.example`. Key vars: `SESSION_SECRET` (required,
  ≥32 chars), `GOSOM_BIN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
  `LINKEDIN_*`, `*_DAILY_CAP`, `LINKEDIN_THROTTLE_SECONDS`.
- `backend/secrets.py` (git-ignored, shipped in the bundle) — baked LinkedIn
  account. `.env` overrides it. Template: `backend/secrets.example.py`.
  ⚠ Rotate the password and move to per-tenant creds before commercial use.

## Where to change things
- Scoring rubrics: `backend/prompts/*.md` + `backend/services/quality.py`
- Related-industry lists: `backend/services/expand.py`
- WhatsApp templates: `backend/services/whatsapp.py`
- LinkedIn mapping: `backend/services/linkedin.py`
- Design tokens: `frontend/styles.css`

## Open items / caveats
- **Live LinkedIn** call not testable in CI; if a real search errors after
  Test-connection passes, adjust the field mapping in `services/linkedin.py`.
  For fresh accounts, prefer **cookie auth** (`LINKEDIN_COOKIE` + `JSESSIONID`).
- LinkedIn scraping has ToS/account risk — dedicated account, low volume.
- Deploy hardening (HTTPS, prod server, backups, multi-user concurrency,
  Postgres, a real job queue) is deferred per the MVP spec.
