# Adaline Lead-Gen Engine — MVP Build Spec

> This is the working specification for an internal sales-team CRM that consumes leads from the gosom Google Maps scraper, scores them with Claude, and surfaces them to the team for outreach. Read this file fully before writing any code.

---

## 1. The Project

**Name:** Adaline Lead-Gen Engine
**Audience:** Internal sales team at Adaline (Myadaline Communications LLP, Calicut). 5–10 users.
**Goal:** Replace ad-hoc spreadsheet lead tracking with a real internal tool. Sales team logs in, runs Google Maps scrapes for target verticals, reviews AI-scored leads, contacts via WhatsApp, tracks pipeline through to closed engagements.

**Status:** MVP. The goal of this build is a working local product the team can actually use. VPS / Docker deployment is **explicitly deferred** — focus on `python -m backend.app` + open `frontend/index.html` in a browser working flawlessly first.

**Source materials in `/reference/`:**
- `Lead_Pipeline_CRM_design_reference.html` — visual design spec. The frontend MUST match this design pixel-for-pixel where reasonable. Read its structure carefully.
- `leadgen_build_doc.html` — architectural context, the tuned scoring prompts (Section 06A/06B), and the operating SOP for the sales team. This is the operational ground truth.
- `gosom_sample_output.json` — example output from the gosom scraper showing the exact JSON shape we consume.

---

## 2. Tech Stack — Locked Decisions

These are not up for debate inside this MVP. They were chosen for "simplest thing that works for a small team."

**Backend:**
- Python 3.11+
- FastAPI (chosen over Flask for type hints, async support, auto-generated API docs at `/docs` which speeds up testing)
- SQLAlchemy 2.x (ORM) + Alembic (migrations)
- SQLite (one file, easy backup, swap for Postgres later — no schema lock-in)
- `passlib[bcrypt]` for password hashing
- `anthropic` Python SDK for Claude scoring
- `uv` for dependency management (fast, modern)

**Frontend:**
- Vanilla HTML + CSS + ES modules JavaScript (no build step, no bundler, no framework)
- Reason: Zo can debug it in browser devtools directly. No build pipeline to maintain. Single `index.html` opens in any browser. When you outgrow vanilla, the rewrite to React is straightforward — but until then, simplicity wins.
- Fetch API for backend calls with `credentials: 'include'`
- Hash-based routing (`#/pipeline`, `#/find`, `#/reports`)

**Auth:**
- Server-side sessions, HMAC-signed httpOnly cookies via FastAPI's `SessionMiddleware`
- bcrypt password hashing (12 rounds)
- No JWT, no OAuth, no third-party auth provider in MVP

**Dev environment:**
- Backend dev: `uv run uvicorn backend.app:app --reload --port 8000`
- Frontend dev: `python -m http.server 5173 --directory frontend`
- API base URL configurable via `API_BASE` constant in `frontend/js/api.js`

**Deferred (do NOT build in MVP):**
- Docker / docker-compose (placeholder file is fine, leave it empty)
- Production WSGI server config
- SSL / HTTPS
- Email or WhatsApp Business API
- Multi-tenancy
- Role-based access control beyond admin/sales distinction
- Audit logs beyond the basic activity table

---

## 3. File Structure

Build exactly this structure. No extra files, no clever layout. If you feel the need to add a folder, ask first.

```
adaline-leadgen-mvp/
├── CLAUDE.md                    # this file
├── README.md                    # quick start: setup, run, seed users
├── .gitignore
├── pyproject.toml               # uv project root
│
├── backend/
│   ├── __init__.py
│   ├── app.py                   # FastAPI entry, mounts routers, middleware
│   ├── config.py                # Pydantic Settings, env vars
│   ├── db.py                    # SQLAlchemy session, engine, get_db dep
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── auth.py                  # hashing, session helpers, login_required
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py              # /api/auth/login, /logout, /me
│   │   ├── leads.py             # /api/leads CRUD, filters, bulk
│   │   ├── jobs.py              # /api/jobs scrape jobs
│   │   └── reports.py           # /api/reports KPIs, charts
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scraper.py           # gosom subprocess wrapper
│   │   ├── scorer.py            # Claude scoring with vertical prompts
│   │   └── whatsapp.py          # URL generation, phone normalization
│   │
│   ├── prompts/
│   │   ├── abaya.md             # abaya vertical scoring prompt
│   │   ├── autoparts_b2b.md     # auto parts B2B scoring prompt
│   │   └── default.md           # fallback for unknown verticals
│   │
│   ├── scripts/
│   │   ├── seed_users.py        # create initial accounts
│   │   └── reset_db.py          # destroy + recreate DB (dev only)
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_leads.py
│       ├── test_jobs.py
│       └── test_scorer.py
│
├── frontend/
│   ├── index.html               # all markup, references styles + js modules
│   ├── styles.css               # design system
│   ├── login.html               # separate login page (no auth = no app)
│   │
│   └── js/
│       ├── app.js               # entry, router, mount
│       ├── store.js             # tiny state management
│       ├── api.js               # fetch wrappers, auth handling
│       │
│       ├── views/
│       │   ├── pipeline.js
│       │   ├── find.js
│       │   ├── reports.js
│       │   └── lead_detail.js
│       │
│       └── components/
│           ├── sidebar.js
│           ├── status_tabs.js
│           ├── lead_row.js
│           ├── lead_detail_panel.js
│           ├── job_card.js
│           ├── pending_review.js
│           └── kpi_card.js
│
├── data/                        # gitignored
│   ├── leads.db                 # SQLite database
│   └── scrapes/                 # gosom output JSON files
│
├── reference/
│   ├── Lead_Pipeline_CRM_design_reference.html
│   ├── leadgen_build_doc.html
│   └── gosom_sample_output.json
│
├── .env.example                 # ANTHROPIC_API_KEY, SESSION_SECRET, GOSOM_BIN
└── docker-compose.yml           # empty placeholder for later
```

---

## 4. Database Schema

Build these models in `backend/models.py`. SQLAlchemy 2.x style with `Mapped[...]` annotations.

```
users
├── id              int, PK
├── username        str, unique, indexed
├── password_hash   str (bcrypt output)
├── role            str  ('admin' | 'sales' | 'viewer')
├── display_name    str
├── created_at      datetime
└── last_login      datetime, nullable

leads
├── id              int, PK
├── scraped_at      datetime
│
├── # from scraper
├── name            str
├── category        str, nullable
├── address         str, nullable
├── city            str, nullable
├── country         str, nullable     ('UAE' | 'KSA' | 'India' | etc.)
├── phone           str, nullable
├── email           str, nullable
├── website         str, nullable
├── rating          float, nullable
├── review_count    int, nullable
├── query_used      str               # the search query that produced this
├── vertical_tag    str               # 'abaya' | 'autoparts_b2b' | 'fuel' | etc.
│
├── # from scorer
├── score           float, nullable
├── qualified       bool, nullable
├── ai_reason       str, nullable
├── scored_at       datetime, nullable
│
├── # sales workflow
├── status          str, default 'pending'
│                   # 'pending' (awaiting approval) | 'new' (in pipeline)
│                   # | 'contacted' | 'replied' | 'meeting' | 'won'
│                   # | 'lost_poor_fit' | 'lost_no_response' | 'lost_declined'
│                   # | 'discarded' (rejected at approval step)
├── assigned_to     int, FK users.id, nullable
├── last_contact    datetime, nullable
├── next_action     str, nullable
├── notes           str, nullable
├── outcome         str, nullable
│
├── # quality control
├── score_flagged   bool, default False
├── flag_reason     str, nullable
├── archived        bool, default False
├── lead_tz         str, default 'Asia/Kolkata'
├── whatsapp_url    str, nullable     # pre-generated
│
└── UNIQUE INDEX on (phone, name) for dedup on insert

jobs
├── id              int, PK
├── query           str               # full search query
├── vertical_tag    str
├── depth           int               # 1, 2, or 3
├── city            str, nullable
├── started_by      int, FK users.id
├── started_at      datetime
├── completed_at    datetime, nullable
├── status          str               # 'queued' | 'running' | 'scoring' | 'done' | 'failed'
├── leads_found     int, default 0
├── leads_scored    int, default 0
├── error_message   str, nullable

activity
├── id              int, PK
├── lead_id         int, FK leads.id
├── user_id         int, FK users.id
├── action          str               # 'status_change' | 'note' | 'assign' | 'contact' | 'flag'
├── detail          str               # JSON-encoded detail
└── created_at      datetime
```

---

## 5. API Endpoints

All `/api/*` routes except `/api/auth/login` require a valid session cookie. Unauthenticated requests return `401`.

| Method | Path | Body | Returns | Notes |
|--------|------|------|---------|-------|
| POST | `/api/auth/login` | `{username, password}` | `{user: {...}}` + session cookie | bcrypt verify, update last_login |
| POST | `/api/auth/logout` | — | `{ok: true}` | clear session |
| GET | `/api/auth/me` | — | `{user: {...}}` | current user info |
| GET | `/api/leads` | query params: `status`, `owner`, `vertical`, `q`, `sort`, `archived`, `limit`, `offset` | `{leads: [...], total: int}` | filter + paginate |
| GET | `/api/leads/{id}` | — | `{lead: {...}, activity: [...]}` | full detail |
| POST | `/api/leads` | `{name, phone, email, city, vertical_tag, ...}` | `{lead: {...}}` | manual add |
| PATCH | `/api/leads/{id}` | partial lead fields | `{lead: {...}}` | update status, notes, etc. logs to activity |
| POST | `/api/leads/bulk` | `{ids: [...], action: 'status' \| 'assign' \| 'archive', value: ...}` | `{updated: int}` | bulk operation |
| POST | `/api/leads/{id}/flag` | `{reason: str}` | `{ok: true}` | flag bad AI score |
| POST | `/api/leads/{id}/approve` | — | `{lead: {...}}` | move from pending → new |
| POST | `/api/leads/{id}/discard` | — | `{ok: true}` | mark as discarded |
| POST | `/api/leads/approve_all` | `{job_id?: int}` | `{approved: int}` | approve all pending (optionally filtered to one job) |
| POST | `/api/jobs` | `{vertical_tag, query, city?, depth}` | `{job: {...}}` | queues a scrape |
| GET | `/api/jobs` | query: `limit`, `status` | `{jobs: [...]}` | list, default last 20 |
| GET | `/api/jobs/{id}` | — | `{job: {...}}` | status + counts |
| GET | `/api/reports/summary` | query: `from`, `to` | `{total, qualified, qual_rate, win_rate, avg_score, new, won, contacted, replied}` | KPI cards |
| GET | `/api/reports/charts` | query: `from`, `to` | `{by_status: [...], by_vertical: [...], funnel: [...], owner_clicks: [...]}` | chart data |

**Conventions:**
- All datetimes returned as ISO 8601 strings in UTC. Frontend converts to IST for display.
- Phone numbers stored as scraped, normalized format generated into `whatsapp_url` at scoring time.
- Errors return `{error: str, detail?: str}` with appropriate HTTP status. Be specific — "username not found" / "password incorrect" not "auth failed."

---

## 6. Auth Implementation

```python
# backend/auth.py — design
from passlib.context import CryptContext
pwd = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)

def hash_password(pw: str) -> str: ...
def verify_password(pw: str, hash: str) -> bool: ...

# Use FastAPI's SessionMiddleware
# In app.py:
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET, max_age=86400, https_only=False, same_site='lax')

# login_required dependency:
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get('user_id')
    if not uid:
        raise HTTPException(401, "not authenticated")
    user = db.get(User, uid)
    if not user:
        request.session.clear()
        raise HTTPException(401, "user no longer exists")
    return user
```

Set `https_only=False` in MVP (we're not on HTTPS yet). Flip to `True` when deploying.

`SESSION_SECRET` comes from `.env`, must be at least 32 chars. Generate in `seed_users.py` if missing.

---

## 7. Scraper Integration (`backend/services/scraper.py`)

gosom CLI invocation pattern:

```bash
google-maps-scraper -input queries.txt -results out.json -depth 1 -exit-on-inactivity 3m
```

Service responsibilities:
- Accept query, depth, city
- Write single-line query file to a temp location
- Launch gosom subprocess with `subprocess.Popen`, capture stdout/stderr for logging
- Poll for completion (or use `asyncio.create_subprocess_exec` in async route)
- On completion, parse the output JSON
- For each lead: dedupe by (phone, name) against existing leads
- Insert new leads with `status='pending'`, `vertical_tag` from job, `query_used` from job
- Update job: `leads_found`, status → `scoring`
- Hand off to scorer
- Final: status → `done`, `completed_at` set

Errors:
- gosom binary not found → job status `failed`, error_message clear
- Timeout (>10 min) → kill process, mark failed
- Empty output → job done with 0 leads, no error

Environment variable `GOSOM_BIN` points to the gosom binary location. Default `/usr/local/bin/google-maps-scraper`.

---

## 8. Claude Scoring (`backend/services/scorer.py`)

Use `anthropic` Python SDK. Model: `claude-haiku-4-5`.

Flow:
1. Load prompt for the lead's vertical (from `backend/prompts/{vertical_tag}.md`)
2. Build user message with the lead's data as JSON
3. Call Claude with `system` (the loaded prompt) and the user message
4. Parse response as strict JSON: `{score: float, qualified: bool, reason: str}`
5. If parse fails: retry once with a "respond with valid JSON only" appended. If still fails: set score=null, qualified=null, ai_reason="scoring error: " + truncated response.
6. Set `scored_at = now()`, update job's `leads_scored` counter
7. Generate `whatsapp_url` via the WhatsApp service

The Anthropic API key comes from `ANTHROPIC_API_KEY` env var. Spend cap enforcement is out of scope for MVP (set in Anthropic console).

**Tuned prompt files are already provided below in Section 13 — write them to `backend/prompts/` exactly as given.**

---

## 9. WhatsApp URL Generation (`backend/services/whatsapp.py`)

```python
def normalize_phone(raw: str, country: str) -> str:
    """Strip non-digits, add country code if missing. Returns digits only."""
    # 971/966/974/973/968/965/91 prefixes mean already international
    # otherwise prepend based on country field

def build_message(lead: Lead) -> str:
    """Return per-vertical first message with {SPECIFIC_DETAIL} placeholder
       intact. Sales rep personalizes before sending."""
    # templates by vertical_tag — abaya, autoparts_b2b, fuel, hospitality, default

def whatsapp_url(lead: Lead) -> str:
    """Return https://wa.me/{phone}?text={urlencoded message}"""
```

Templates are in Section 14 below.

---

## 10. Frontend Design Fidelity

This is non-negotiable. The frontend MUST visually match `reference/Lead_Pipeline_CRM_design_reference.html`. Open that file in your browser before writing any CSS.

**Design system to extract into `frontend/styles.css`:**

```
Colors (dark theme — default):
  --bg:        #0a0a0b      (page background)
  --surf2:    #131316      (cards, panels)
  --surf3:    #1c1c20      (hover, deeper surface)
  --line:     #262630      (borders)
  --linesoft: #1c1c20      (subtle dividers)
  --line2:    #363641      (emphasis borders)
  --ink:      #f4f1ea      (primary text)
  --ink2:     #d6d0c4      (secondary text)
  --ink3:     #8a847a      (tertiary text)
  --ink4:     #56524a      (muted text)
  --acc:      #b4ff39      (lime acid green — THE accent)
  --acc-ink:  #b4ff39      (text version of accent)

Colors (light theme — toggled):
  Invert: bg→#f4f1ea, ink→#0a0a0b, etc.
  Keep --acc identical in both themes.

Typography:
  --display:  'Space Grotesk', sans-serif    (weights 600/700/800)
  --body:     'Inter', sans-serif             (400/500/600/700)
  --mono:     'JetBrains Mono', monospace     (400/500/700)

  Sizes:
  - Display titles: 23px-64px
  - Headings: 14-18px
  - Body: 13-14px
  - Mono labels/kickers: 10-11px with 0.1-0.16em letter-spacing, UPPERCASE

Spacing:
  Mostly multiples of 4px. Card padding ~22px. Section gaps ~28px.

Radii:
  Buttons / inputs: 6-7px
  Cards: 8-10px
  Pills / chips: 4px

Shadows:
  Minimal. Use border emphasis (--line2) instead of shadow.
  Status dot on logo has glow: box-shadow: 0 0 12px var(--acc).
```

**Layout matches the design reference:**
- Login: centered 344px card, lime-dot + wordmark, two inputs + sign-in button
- App shell: 220px sidebar + main content area
- Sidebar: brand (top), nav (middle), theme toggle (bottom), user (very bottom with sign-out)
- Three views: Pipeline (default), Find Leads, Reports

**Components to build (read the design ref for visual specifics):**
- `sidebar.js`: brand block, nav items with dot + label + count, theme toggle row, user card with avatar + name + role + logout
- `status_tabs.js`: horizontal tabs for status filter, count badge on each
- `lead_row.js`: row in pipeline list — checkbox, score, name+sub, city, status dot+label, owner pill, click → opens detail
- `lead_detail_panel.js`: right-side slide-in panel with full lead info, activity log, action buttons (WhatsApp launch, copy phone, copy email, status change, notes), prev/next navigation
- `job_card.js`: shows a running or recent scrape job with status, query, count, when
- `pending_review.js`: card for a pending lead with approve / discard buttons
- `kpi_card.js`: reports view stat card with number + label + delta arrow

**State management (`frontend/js/store.js`):**

Build a minimal reactive store. Not Redux. Not even Zustand. Just:

```javascript
// store.js
const state = { user: null, view: 'pipeline', leads: [], filters: {...}, ... };
const listeners = new Set();
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function getState() { return state; }
export function update(patch) {
  Object.assign(state, patch);
  listeners.forEach(fn => fn(state));
}
```

Views subscribe on mount, unsubscribe on unmount. That's it. No virtual DOM. Re-render by direct DOM updates inside the view.

**Routing:**

Hash router only. `window.location.hash = '#/find'`. On `hashchange`, view dispatcher mounts the matching view component.

---

## 11. Build Sequence — Phases & Acceptance Criteria

**Build in this exact order. Do NOT skip ahead. Confirm each phase's acceptance criteria before starting the next.**

### Phase 1 — Backend skeleton + auth

**Tasks:**
- Project scaffold (`pyproject.toml`, `uv sync`)
- `backend/app.py` with FastAPI, SessionMiddleware, CORS for localhost frontend
- `backend/models.py` with User, Lead, Job, Activity
- `backend/db.py` with engine, sessionmaker, `get_db` dependency
- Alembic init + initial migration creating all tables
- `backend/auth.py` with hashing + `current_user` dep
- `backend/routers/auth.py` with login/logout/me
- `backend/scripts/seed_users.py` — creates these 5 accounts:
  - `jareer` / role admin / display "Jareer"
  - `ibrahim` / role admin / display "Ibrahim"
  - `aslam` / role sales / display "Aslam"
  - `shijas` / role sales / display "Shijas"
  - `sales1` / role sales / display "Sales Rep"
  - Default password for all: `change_me_first_login` (note in README that this must be changed)
- Tests for auth flow: register hash, login success, login fail, /me, logout

**Acceptance:**
```bash
uv run uvicorn backend.app:app --reload
uv run python -m backend.scripts.seed_users
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"aslam","password":"change_me_first_login"}' -c cookies.txt -i
# should return 200 with Set-Cookie
curl http://localhost:8000/api/auth/me -b cookies.txt
# should return {"user": {"id": 3, "username": "aslam", "role": "sales", "display_name": "Aslam"}}
uv run pytest backend/tests/test_auth.py -v
# all tests pass
```

**STOP. Demonstrate above works. Then proceed to Phase 2.**

### Phase 2 — Leads CRUD + filter + sample data

**Tasks:**
- `backend/routers/leads.py` — all endpoints from Section 5
- `backend/schemas.py` — Pydantic schemas for requests/responses
- `backend/scripts/seed_leads.py` — drop 30 fake leads in mixed verticals/statuses for frontend dev
- Tests: list with filters, get one, patch status, bulk update

**Acceptance:**
```bash
uv run python -m backend.scripts.seed_leads
curl 'http://localhost:8000/api/leads?status=new&limit=10' -b cookies.txt
# returns leads array
curl -X PATCH 'http://localhost:8000/api/leads/1' -b cookies.txt -H "Content-Type: application/json" -d '{"status":"contacted","notes":"reached out via WA"}'
# 200, lead updated, activity row created
uv run pytest backend/tests/test_leads.py -v
```

**STOP. Demonstrate. Proceed.**

### Phase 3 — Frontend rebuild with design fidelity

**Tasks:**
- `frontend/styles.css` — full design system extracted from reference HTML
- `frontend/login.html` — standalone login page
- `frontend/index.html` — app shell
- `frontend/js/api.js` — fetch wrappers
- `frontend/js/store.js` — minimal store
- `frontend/js/app.js` — router + view mounting
- All view files (`pipeline.js`, `find.js`, `reports.js`)
- All component files
- Wire Pipeline view to `/api/leads` — real data flows
- Wire login/logout properly
- Dark/light theme toggle works and persists in localStorage

**Acceptance:**
- Open `frontend/login.html` → log in as aslam → land on pipeline
- Pipeline shows seeded leads, status tabs work, search works, sort works
- Click lead → detail panel slides in
- Status change persists (refresh page → still updated)
- Theme toggle works
- Side-by-side comparison with reference HTML: 95%+ visual match
- All views render without console errors
- Mobile breakpoint (< 768px): sidebar collapses, layout reflows reasonably

**STOP. Show screenshots side-by-side with reference. Proceed.**

### Phase 4 — Reports view + KPIs

**Tasks:**
- `backend/routers/reports.py` — summary + charts endpoints
- `frontend/js/views/reports.js` — KPI cards + charts
- Use a tiny chart library or hand-roll SVG bars/donut (no Chart.js for MVP — keep it simple)

**Acceptance:**
- Reports view shows real KPIs from seeded data
- Charts render: by_status donut, by_vertical bars, funnel, owner leaderboard
- Numbers tie out: total leads on report matches count from /api/leads

**STOP. Demo. Proceed.**

### Phase 5 — Scraper + scorer integration

**Tasks:**
- `backend/services/scraper.py` — gosom subprocess wrapper
- `backend/services/scorer.py` — Claude scoring with vertical prompts
- `backend/services/whatsapp.py` — URL generation
- `backend/prompts/abaya.md`, `autoparts_b2b.md`, `default.md` (content from Section 13)
- `backend/routers/jobs.py` — start, list, approve, discard
- Background job execution — use FastAPI's `BackgroundTasks` for MVP (good enough for single-user concurrency at this scale)
- Frontend Find Leads view wired to jobs API
- Pending review queue in Find Leads view

**Acceptance:**
- From frontend Find Leads view: select vertical "abaya", type query "abaya boutiques Dubai Marina", depth 1, click Start
- Job appears in jobs list with "running" status
- gosom runs (you'll see logs), then "scoring" status, then "done"
- Pending review section populates with scored leads
- Each pending lead shows: name, score, ai_reason, approve / discard buttons
- Approve → moves to pipeline as "new" status
- Discard → marks as discarded, doesn't show in pipeline

**At this point the MVP is complete and usable. STOP here for MVP delivery.**

---

## 12. Standing Rules — Adaline-Specific

These overrule any generic best-practice instincts:

1. **Lime acid green `#b4ff39` is THE accent.** Not yellow. Not any other green. Use it sparingly — for the brand dot, the primary button, the active tab indicator, and key highlights. Never for body text, never for large fills.

2. **Typography hierarchy is sacred:** Space Grotesk for display (always 600+ weight), Inter for body, JetBrains Mono for utility labels and code. Don't mix.

3. **Dark theme is the default.** Light theme is the secondary toggle. Both must look polished. The lime accent should NOT change between themes.

4. **Honest error messages.** "Username not found" beats "Authentication failed." "Invalid phone format — expected +971 50..." beats "Validation error." The user is a teammate, not a stranger.

5. **All currency is Indian format.** `₹2,07,000` not `₹207,000` not `$2,500`.

6. **All UI times in IST (Asia/Kolkata).** Storage in UTC.

7. **WhatsApp deep links use `https://wa.me/{digits}?text={encoded}`** — never the `whatsapp://` URI scheme (broken on iOS Safari).

8. **Never log passwords.** Never store them plain. Never echo them back in error messages.

9. **No tracking, no analytics, no third-party scripts** in the frontend. This is an internal tool.

10. **The status taxonomy is fixed:** `pending`, `new`, `contacted`, `replied`, `meeting`, `won`, `lost_poor_fit`, `lost_no_response`, `lost_declined`, `discarded`. Do not add or rename without explicit instruction.

11. **All Python code uses type hints, modern syntax** (3.11+ features: `list[str]` not `List[str]`, `X | None` not `Optional[X]`, match/case where appropriate).

12. **All JS uses ES modules, async/await, no callbacks.** No jQuery. No lodash. No build tools. Vanilla.

13. **Tests are required for backend logic.** Not for UI rendering. Use `pytest` + `httpx.AsyncClient` for FastAPI testing.

14. **Commits should be atomic and well-described.** "Add login endpoint" not "stuff" or "WIP". If using git, commit after each phase's acceptance criteria pass.

---

## 13. Tuned Scoring Prompts (write to `backend/prompts/`)

### `abaya.md`

```
You are a B2B lead-qualification analyst for Adaline, a brand and technology studio in Calicut serving premium clients across Kerala and the Gulf. You score each business 0.0–10.0 on fit for our services: brand strategy, content production, web/app development, customer engagement systems.

VERTICAL: ABAYA / PREMIUM MODEST FASHION

SCORE 8.0–10.0 (qualified-high — Aslam works these first):
  · Rating >= 4.5 AND review_count >= 100
  · Has working website (any .ae / .sa / .qa / .bh / .kw / .om TLD is a strong signal; .com with brand-style domain also strong)
  · Located in PREMIUM RETAIL DISTRICT — Dubai (Marina, Downtown, JBR, City Walk, Mall of the Emirates area), Sharjah (Al Wahda, Al Majaz, Sahara Centre area), Abu Dhabi (Khalidiya, Marina Mall, Yas Mall area), Riyadh (Olaya, Tahlia, King Fahd Rd), Jeddah (Tahlia, Andalus), Doha (Pearl, Lusail, West Bay)
  · Business name suggests BRAND, not commodity:
    OK   "Hessa Boutique", "Al Noor Abaya", "Modanisa Atelier"
    NO   "Al Wahda General Trading", "Best Fashion Wholesale"
  · Multiple location listings = chain operator = enterprise-class

SCORE 5.0–7.9 (qualified-medium — Aslam queues for week 2):
  · Rating >= 4.0 OR review_count >= 50 (one of two)
  · Has website (any quality, even Linktree-style)
  · GCC location but not premium district
  · Single outlet, brand-style name

SCORE 0.0–4.9 (unqualified — skip):
  · Mall kiosk, generic souk shop
  · No website AND no instagram link in listing
  · Rating < 4.0 with > 20 reviews (real signal of poor service)
  · "Trading", "Wholesale", "General Stores", "Cash & Carry" in name
  · Outside GCC (we serve GCC abaya market)

Return strict JSON only, no preamble:
{
  "score": 7.5,
  "qualified": true,
  "reason": "one sentence, max 160 chars, Aslam reads in 2 seconds"
}

qualified = true if score >= 5.0, false otherwise.

Example reasons:
  "Premium abaya brand, Dubai Marina, 4.8★, working site — ALIFA-shape fit"
  "Single-outlet boutique Sharjah, 4.2★, IG-only — queue week 2"
  "Generic abaya wholesale Karama, no brand signals — skip"
```

### `autoparts_b2b.md`

```
You are a B2B lead-qualification analyst for Adaline, a brand and technology studio in Calicut serving premium clients across Kerala and the Gulf. You score each business 0.0–10.0 on fit for our services: brand strategy, content production, web/app development, customer engagement systems.

VERTICAL: AUTO PARTS B2B DISTRIBUTION

SCORE 8.0–10.0 (qualified-high — wholesale distributors):
  · Business name has WHOLESALE / DISTRIBUTION signals:
    "spare parts wholesale", "auto parts distributor",
    "OEM supplier", "parts & accessories trading"
  · Located in INDUSTRIAL / TRADE ZONE:
    - Riyadh: Sulay Industrial, 2nd / 3rd Industrial City
    - Jeddah: Industrial City, Al Khumra
    - Dammam: 1st / 2nd Industrial City, Al Jubail
    - Dubai: Industrial City, Jebel Ali Free Zone, Al Quoz
    - Sharjah: Industrial Area 1-13
  · Multiple branch listings = distribution network operator
  · Working website with B2B signals (catalog, dealer login, bulk pricing, "for trade enquiries" type messaging)
  · Operating hours are commercial (Sun-Thu 8 AM-5 PM type), not retail

SCORE 5.0–7.9 (qualified-medium — hybrid retail/wholesale):
  · Located in industrial-adjacent area
  · Has website but unclear B2B model
  · Single outlet but in trade zone
  · Established (review count > 50)

SCORE 0.0–4.9 (unqualified — skip):
  · Pure retail: storefront walk-in counter
  · Auto service garage (they BUY from distributors, they're not our customer)
  · Tire shops, oil change, car wash (adjacent industry, not fit)
  · No website AND no review activity
  · Outside KSA / UAE (Phase 2 markets)

Return strict JSON only:
{
  "score": 7.5,
  "qualified": true,
  "reason": "max 160 chars"
}

Example reasons:
  "Wholesale distributor Riyadh 2nd Industrial, 3 branches — Roca-shape fit"
  "Hybrid retail/trade Dubai Al Quoz, has site — queue week 2"
  "Pure retail counter Karama — skip, not our model"
```

### `default.md`

```
You are a B2B lead-qualification analyst for Adaline. Score this business 0.0–10.0 on fit for our services (brand, content, tech, customer engagement).

Without a specific vertical rubric, score conservatively:
- 7+ requires: rating >= 4.5, review_count >= 50, working website, located in Kerala or GCC
- 5-6: some positive signals but unclear fit
- < 5: weak signals or wrong category

Return strict JSON: {"score": X, "qualified": bool, "reason": str (max 160 chars)}
```

---

## 14. WhatsApp Templates (in `backend/services/whatsapp.py`)

```python
TEMPLATES = {
    'abaya': (
        "Hi! Saw {name} — really like the brand. We're Adaline, a brand "
        "and content studio in Calicut working with abaya labels across "
        "the GCC. Currently working with ALIFA (Dubai). Open to a quick "
        "15-min conversation?\n\n— Aslam, Adaline"
    ),
    'autoparts_b2b': (
        "Hi! Came across {name} — looks like a serious operation in {city}. "
        "We're Adaline, building digital systems for auto-parts distributors "
        "in the GCC. Currently working with Roca Group on Saudi expansion. "
        "Open to a peer call?\n\n— Aslam, Adaline (Calicut)"
    ),
    'fuel': (
        "Hi! Saw {name} on Google. We're Adaline, running a 36-month brand "
        "programme with Roca Fuels (MRPL dealer in Calicut) — websites, "
        "content, customer engagement. Open to a quick walk-through of "
        "what's working?\n\n— Aslam, Adaline"
    ),
    'hospitality': (
        "Hi! Came across {name} — love the look. We're Adaline, a brand "
        "studio in Calicut working with boutique hospitality on identity, "
        "photography, and direct-booking websites. Open to a quick chat "
        "if direct-channel growth is on your radar?\n\n— Aslam, Adaline"
    ),
    'default': (
        "Hi! Came across {name} on Google. We're Adaline, a brand and tech "
        "studio in Calicut working with premium businesses across Kerala "
        "and the Gulf. Open to a short conversation about what we do?\n\n— Aslam, Adaline"
    ),
}
```

---

## 15. Environment Variables (`.env.example`)

```
# Server
SESSION_SECRET=replace_with_32_plus_random_chars_use_openssl_rand
PORT=8000

# Database
DATABASE_URL=sqlite:///./data/leads.db

# Claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5

# Scraper
GOSOM_BIN=/usr/local/bin/google-maps-scraper
SCRAPE_OUTPUT_DIR=./data/scrapes
SCRAPE_TIMEOUT_SECONDS=600

# Frontend (for CORS)
FRONTEND_ORIGIN=http://localhost:5173
```

`SESSION_SECRET` MUST be set. Refuse to start if missing or shorter than 32 chars. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and put in README.

---

## 16. README.md Skeleton

Generate a README.md that covers:

1. **What this is** (one paragraph)
2. **Tech stack** (one paragraph)
3. **Local setup** — `uv sync`, copy `.env.example` to `.env`, fill values, run migrations, seed users, start backend, open frontend
4. **First login** — usernames + default password + "CHANGE THIS FIRST"
5. **Adding gosom** — install gosom locally, set `GOSOM_BIN` env var, test it from a Find Leads search
6. **Running tests** — `uv run pytest`
7. **Project structure** — brief tree
8. **Where to make changes** — "scoring prompts in `backend/prompts/`", "WhatsApp templates in `services/whatsapp.py`", "design tokens in `frontend/styles.css`"

Keep it short. README is for Zo to bring up the project on a new machine.

---

## 17. What's Out of Scope (do NOT build)

- Email outreach / SMTP integration
- WhatsApp Business API (BSP integration is Phase 2 later)
- Multi-organization / multi-tenant
- Password reset flow (admin manually resets for MVP)
- 2FA
- File uploads for leads (CSV import comes Phase 1.5)
- Reports CSV export (button can stub out for MVP)
- Notifications / email digest
- Activity feed beyond basic per-lead log
- Lead deduplication across queries (basic phone+name unique constraint is enough)
- AI prompt editor in UI (prompts edited as .md files for now)
- Audit log of admin actions
- Backup automation
- Production logging / metrics / observability

---

## 18. Initial Prompt to Use With Claude Code

Once this file is in your project root, start your Claude Code session with:

> Read CLAUDE.md fully. Confirm you understand the project, the tech stack, the file structure, and the phase sequencing. Then start with Phase 1 — backend skeleton plus auth. Build all the Phase 1 files, write the tests, and demonstrate the acceptance criteria pass. Do not start Phase 2 until I confirm. Ask if anything in CLAUDE.md is ambiguous before writing code.

---

## 19. Glossary

- **gosom** — the open-source Google Maps scraper at github.com/gosom/google-maps-scraper
- **Vertical** — a business category we target (abaya, auto parts B2B, fuel retail, hospitality, etc.)
- **Pending lead** — a lead that's been scraped + scored but not yet approved into the pipeline by a sales rep
- **Pipeline** — leads with status `new`, `contacted`, `replied`, `meeting`, `won` (active workflow)
- **ALIFA** — live client, premium abaya brand based in Dubai. Anchor case study for abaya vertical.
- **Roca Group** — live client, auto parts B2B in Saudi Arabia. Anchor case study for autoparts vertical.
- **Roca Fuels** — separate live client, MRPL fuel station in Calicut. Anchor case study for fuel vertical.
- **The Management** — used in client-facing documents. NOT used here (this is internal).
- **Phase 1.5** — features deferred until MVP is shipped and validated, but planned: CSV import, reports CSV export, prompt tuning UI, batch operations expansion.

---

End of CLAUDE.md. Begin Phase 1 when prompted.
