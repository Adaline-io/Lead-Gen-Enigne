# Adaline Lead-Gen Engine

Internal sales CRM for **Adaline** (Myadaline Communications LLP, Calicut). It
consumes leads from the [gosom Google Maps scraper](https://github.com/gosom/google-maps-scraper),
scores them for fit with Claude, and surfaces them to the sales team for
WhatsApp outreach and pipeline tracking. Built to replace ad-hoc spreadsheet
lead tracking for a 5–10 person team.

## How it works

End to end, the engine runs one loop: **find → score → review → work → report.**

1. **Find** — an admin opens **Find Leads**, picks a source (**Google Maps** or
   **LinkedIn**) and types an industry + location. The app expands that industry
   into distinct *related* categories (the whole market, not synonyms), searches
   them all, and de-duplicates the results into the database as `pending` leads.
2. **Score** — every new lead is scored **0–10** automatically by a data-driven
   quality engine built from its own fields (rating, reviews, website, location
   and name signals). With an `ANTHROPIC_API_KEY` set, Claude refines the score
   using the per-vertical prompts; without one, the deterministic score stands.
3. **Review** — scored leads land in a **review queue**. The admin **approves**
   the good ones (which assigns each to a rep — Approve-all round-robins the
   team) or **discards** the rest.
4. **Work** — reps see only their assigned leads in the **Pipeline**, move them
   through statuses (`new → contacted → replied → meeting → won` / `lost_*`),
   add notes/next-actions, and message via **one-click WhatsApp** deep links
   with a per-vertical opening template.
5. **Report** — **Reports** rolls everything up: KPI cards, a status donut,
   by-vertical bars, the funnel, a follow-up list, and per-rep performance
   (leads / confirmed / target / achieved).

It's a **single process**: FastAPI serves both the API and the frontend, with
SQLite for storage, so the whole thing runs from `./run.sh` with no separate
servers, build step, or deploy infra.

### Keeping it updated

The code lives on GitHub (`main` is the live branch). To pull the latest and
reload on any machine:

```bash
git pull origin main      # get the newest code
uv sync                   # install any new dependencies
uv run alembic upgrade head   # apply any new DB migrations
./run.sh                  # restart the app (Ctrl+C to stop first)
```

Your local `.env`, `backend/secrets.py`, and `data/` are git-ignored, so a pull
never overwrites your config, credentials, or database. After editing prompts,
templates, or frontend files, just restart (or rely on `--reload` in dev) — a
browser refresh picks up frontend changes.

## Tech stack

Python 3.11 · FastAPI · SQLAlchemy 2.x + Alembic · SQLite · passlib[bcrypt] ·
Anthropic SDK, managed with [`uv`](https://docs.astral.sh/uv/). Frontend is
vanilla HTML/CSS/ES-module JavaScript (no build step). Auth is server-side
HMAC-signed cookie sessions. This is a **local-first MVP** — Docker/VPS
deployment is deferred.

> Built at the repo root (not a nested folder). Alembic owns the schema, but
> `seed_users` and app startup also run `create_all()` so first-run works
> without a manual migrate step.

## Quick start (one command)

The easiest way — installs deps, sets up the DB, seeds demo data, and launches
both servers, then opens the app:

```bash
./run.sh           # macOS / Linux
run.bat            # Windows (double-click or run in a terminal)
```

Then log in at **http://localhost:8000/** as `aslam` /
`admin`. Press `Ctrl+C` to stop. Use `./run.sh --fresh` to wipe
and reseed.

> **One process.** The backend serves the frontend, so a single
> `uvicorn` runs the whole app at `http://localhost:8000/` — no second
> terminal, and the login cookie is same-origin so nothing to configure.

## Local setup (manual)

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

# 5. Run the app (one process serves API + frontend)
uv run uvicorn backend.app:app --reload --port 8000
#    Open      http://localhost:8000/
#    API docs: http://localhost:8000/docs
```

> Open **http://localhost:8000/** — the backend serves the frontend, so there's
> only one server. (Don't use the `file://` path — the session cookie needs
> HTTP.)
>
> **Optional two-terminal dev mode:** if you'd rather edit the frontend with a
> separate static server, run `python3 -m http.server 5173 --directory frontend`
> and open `http://localhost:5173/login.html`; `frontend/js/api.js` auto-points
> at the backend on `:8000` in that case.

## First login

Seeded accounts (all share the same default password):

| Username  | Role   | Display name |
|-----------|--------|--------------|
| `jareer`  | admin  | Jareer       |
| `ibrahim` | admin  | Ibrahim      |
| `aslam`   | sales  | Aslam        |
| `shijas`  | sales  | Shijas       |
| `sales1`  | sales  | Sales Rep    |

**Default password:** `admin` (shared by all accounts for now) — **⚠ CHANGE
THIS ON FIRST LOGIN.** There is no password-reset flow in the MVP; an admin
resets manually (re-running `seed_users` resets everyone back to `admin`).

### Who can do what (roles)

| Action | Admin | Sales rep | Viewer |
|---|:--:|:--:|:--:|
| Run scrapes (Find Leads) | ✅ | — | — |
| Approve / discard pending leads | ✅ | — | — |
| Assign / re-assign owners | ✅ | — | — |
| Import CSV | ✅ | — | — |
| Add a lead manually | ✅ | ✅ | — |
| Work leads (status, notes, next action, flag) | ✅ | ✅ | — |
| Export CSV, view Pipeline & Reports | ✅ | ✅ | ✅ |

**The workflow:** an **admin** runs a search, reviews the AI-scored results, and
**approves** the good ones — each approved lead is **assigned to a rep** to work
(Approve-all round-robins across the team; a single Approve assigns to the admin
who approved it). **Sales reps** then work their assigned leads through the
pipeline. The Find Leads screen is hidden from reps, so not everyone is firing
off scrapes.

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

Plus quality-of-life logic that "just works":
- **Data-driven quality scoring** — every lead scored 0–10 from its own fields.
- **CSV import / export** — bring in a spreadsheet or gosom export (auto-mapped,
  scored, deduped); export the filtered pipeline. Buttons on the Pipeline view.
- **Smart de-duplication** — across scrapes and imports (phone / name+city / domain).
- **Auto-assign** — approving a lead assigns it to you; Approve-all round-robins
  across the team.
- **Follow-up tab** — surfaces active leads with no contact for 3+ days.
- **Existing-client guard** — flags leads matching live clients (ALIFA / Roca).
- **Responsive UI** — works on phone, tablet and desktop.

Backend test suite: `uv run pytest` (89 tests).

### How the search query + filtering work

gosom runs **exactly the way it's meant to** — it gets a clean industry +
location query (e.g. `abaya boutiques Dubai Marina`) and returns **every lead**
Google Maps has. The app's only job is to **filter the data sheet** afterwards:

1. **Junk filter (always on):** rows with no real contact data — no phone,
   email, website *or* address — are dropped. Every real, contactable lead is
   kept.
2. **Keyword filter (optional):** anything you type in **Keywords** (e.g.
   `premium`, `wholesale`) narrows the kept rows to those matching across name /
   category / address / website. Leave it blank to keep them all.

Keywords are **never** folded into the gosom query itself (searching the literal
phrase `abaya boutique premium` on Google Maps returns junk) — they only filter
the results.

### Finding leads: sources + related-category expansion

On **Find Leads** (admin only) you choose **where to search** — **Google Maps**
or **LinkedIn** — and type an industry. The app doesn't just search that exact
phrase: it expands it into **distinct related industries** — the whole market
ecosystem, not reworded synonyms. e.g. "abaya boutiques" → modest fashion,
islamic clothing, hijab stores, kaftan, bridal wear, tailoring, textile shops,
perfume & oud… (never "abaya store / abaya shop"). It searches them all and
dedupes, so you capture the full related market. Click **✨ Suggest related** to see/edit
the categories as chips, or leave **"Also search related categories"** on to
auto-expand. With an `ANTHROPIC_API_KEY` set, the expansion is generated by
Claude for *any* industry; otherwise a built-in list is used.

### LinkedIn source (optional)

The LinkedIn source uses **[linkedin-api](https://github.com/tomquirk/linkedin-api)**
to search LinkedIn by **industry/keyword** and return companies — a natural fit
for the Find Leads box. It's **off by default** and falls back to clearly-labelled
demo data, so the flow works locally without it. The Find Leads screen shows a
**live / demo** badge under the source selector so you always know which you're
getting. To enable real LinkedIn:

```bash
uv pip install linkedin-api
```
then in `.env`:
```ini
LINKEDIN_ENABLED=true
LINKEDIN_USER=you@example.com     # a DEDICATED LinkedIn account
LINKEDIN_PASS=your-password
```
Restart the app. LinkedIn results map the **company** to the lead and keep the
LinkedIn page as the website; radius/depth/email-extraction are Google-Maps-only
and are hidden when LinkedIn is selected.

> ⚠ Scraping LinkedIn may violate its Terms of Service and can get accounts
> restricted/banned. Use a **dedicated** account, keep volumes low, and confirm
> it's acceptable before enabling. Treat LinkedIn as supplementary to Google Maps.

### Scraping: demo mode vs live Google Maps

The find → review → approve flow **works out of the box**, even without the
scraper installed:

- **Demo mode (default, `SCRAPER_DEMO=true`)** — when the gosom binary isn't
  present, a search returns realistic *sample* leads (clearly labelled
  "sample lead (demo scrape)" in the address) so you can try the whole flow
  locally. They're scored and de-duplicated like real ones.
- **Live mode** — install gosom and the same searches pull **real Google Maps
  businesses**. Demo mode is ignored automatically once gosom is found.

**To turn on live Google Maps scraping:**
1. Install gosom: https://github.com/gosom/google-maps-scraper
   (it's a single Go binary — follow their README; e.g. `go install` or grab a
   release, then note the path to the `google-maps-scraper` executable).
2. In `.env`, set `GOSOM_BIN` to that path
   (default `/usr/local/bin/google-maps-scraper`).
3. Optionally set `SCRAPER_DEMO=false` to require the real binary, and set
   `ANTHROPIC_API_KEY` so Claude refines the scores (otherwise the built-in
   data-driven engine scores every lead).
4. Restart the backend. Run a search from **Find Leads** (as an admin).

### How leads get scored

Every lead is scored 0–10 by a **deterministic, data-driven quality engine**
(`backend/services/quality.py`) computed from the lead's own fields — rating,
review count, website/TLD, premium-district / industrial-zone location signals,
brand-vs-commodity name signals, and country — following the vertical rubrics.
`qualified` is `score >= 5.0`. This is the baseline, so **leads are always
scored and explainable even without an Anthropic key** (and manually added
leads are scored on save).

If `ANTHROPIC_API_KEY` is set, Claude refines the score using the vertical
prompts in `backend/prompts/`; if that call fails for any reason, the system
falls back to the data-driven score rather than leaving the lead unscored.
