"""LinkedIn lead source (optional) — industry/keyword search.

Backed by the open-source **linkedin-api** (https://github.com/tomquirk/linkedin-api),
which searches LinkedIn by keyword and returns companies/people — a natural fit
for "type an industry, get leads". Mirrors the gosom integration: it returns
records in the same shape the scraper maps to leads.

Off by default (LINKEDIN_ENABLED=false); falls back to clearly-labelled demo
data so the flow works locally without credentials.

⚠ Scraping LinkedIn may violate its Terms of Service and can get accounts
restricted. Use a dedicated account, keep volumes low, and confirm it's
acceptable before enabling.
"""

from __future__ import annotations

import re

from backend.config import settings

# Cache the authenticated client across calls in one process.
_client = None


def linkedin_live() -> bool:
    """True when real LinkedIn scraping is configured (else demo/off)."""
    return bool(settings.LINKEDIN_ENABLED and settings.LINKEDIN_USER and settings.LINKEDIN_PASS)


def test_connection() -> dict:
    """Verify LinkedIn credentials before a full scrape. {ok, message}."""
    if not settings.LINKEDIN_ENABLED:
        return {"ok": False, "message": "LinkedIn is disabled. Set LINKEDIN_ENABLED=true in .env."}
    if not (settings.LINKEDIN_USER and settings.LINKEDIN_PASS):
        return {"ok": False, "message": "Add LINKEDIN_USER and LINKEDIN_PASS in .env."}
    try:
        global _client
        _client = None  # force a fresh login for the test
        _get_client()
        return {"ok": True, "message": f"Connected to LinkedIn as {settings.LINKEDIN_USER}."}
    except ModuleNotFoundError:
        return {"ok": False, "message": "linkedin-api not installed. Run: uv pip install linkedin-api"}
    except Exception as exc:
        return {"ok": False, "message": f"Login failed: {type(exc).__name__}: {exc}"[:200]}


def _demo_records(query: str, city: str | None) -> list[dict]:
    """Sample LinkedIn-style results (companies + a contact) for local testing."""
    import random

    rng = random.Random(hash(("li", query, city)) & 0xFFFFFFFF)
    place = (city or "Dubai").strip()
    base = (query or "Business").strip().title()
    first = ["Aisha", "Omar", "Layla", "Khalid", "Sara", "Yusuf", "Mona", "Tariq"]
    roles = ["Founder", "Managing Director", "Head of Marketing", "CEO",
             "Operations Manager", "Business Development Lead"]
    out: list[dict] = []
    for i in range(rng.randint(5, 8)):
        company = f"{base.split()[0]} {rng.choice(['Group','Labs','Co','Studio'])} {place}"
        out.append({
            "title": company,
            "category": rng.choice(roles),
            "address": f"{place} — sample LinkedIn lead (demo)",
            "city": place,
            "website": f"https://www.linkedin.com/company/{base.split()[0].lower()}{i}",
            "emails": [],
            "phone": None,
            "review_rating": None,
            "review_count": None,
            "contact_name": f"{rng.choice(first)} {chr(65 + i)}.",
        })
    return out


def _get_client():
    global _client
    if _client is not None:
        return _client
    from linkedin_api import Linkedin  # lazy import — optional dependency

    _client = Linkedin(settings.LINKEDIN_USER, settings.LINKEDIN_PASS)
    return _client


def _company_id(item: dict) -> str | None:
    # search_companies items vary by version; try the common shapes.
    for key in ("public_id", "publicIdentifier", "urn_id", "urnId"):
        val = item.get(key)
        if val:
            return str(val).split(":")[-1]
    urn = item.get("urn") or item.get("targetUrn") or ""
    m = re.search(r"(\d+)$", str(urn))
    return m.group(1) if m else None


def _linkedinapi_records(query: str, city: str | None, limit: int) -> list[dict]:
    """Real LinkedIn search via linkedin-api. Defensive against shape changes."""
    api = _get_client()
    keywords = " ".join(p for p in (query, city) if p).strip()

    try:
        companies = api.search_companies(keywords=[keywords], limit=limit or 25) or []
    except TypeError:
        companies = api.search_companies(keywords, limit=limit or 25) or []

    records: list[dict] = []
    for c in companies:
        if not isinstance(c, dict):
            continue
        name = c.get("name") or c.get("title")
        if not name:
            continue
        loc = c.get("headquarter") or c.get("location") or c.get("subline") or city
        cid = _company_id(c)
        url = f"https://www.linkedin.com/company/{cid}" if cid else None
        records.append({
            "title": name,
            "category": c.get("subline") or c.get("industry"),
            "address": loc,
            "city": city or (loc if isinstance(loc, str) else None),
            "website": url,
            "emails": [],
            "phone": None,
            "review_rating": None,
            "review_count": None,
        })
    return records


def run_linkedin(query: str, city: str | None, limit: int | None = None) -> list[dict]:
    """Return LinkedIn lead records (or demo data when not configured)."""
    if not settings.LINKEDIN_ENABLED:
        if settings.SCRAPER_DEMO:
            return _demo_records(query, city)
        raise RuntimeError(
            "LinkedIn source is disabled. Set LINKEDIN_ENABLED=true (and "
            "LINKEDIN_USER / LINKEDIN_PASS) to enable it."
        )
    if not (settings.LINKEDIN_USER and settings.LINKEDIN_PASS):
        raise RuntimeError("Set LINKEDIN_USER and LINKEDIN_PASS in .env to use LinkedIn.")
    try:
        return _linkedinapi_records(query, city, limit or 25)
    except ModuleNotFoundError:
        raise RuntimeError("linkedin-api is not installed. Run: uv pip install linkedin-api")
    except Exception as exc:  # auth/challenge/rate-limit — surface a clear message
        raise RuntimeError(f"LinkedIn search failed: {type(exc).__name__}: {exc}"[:240])
