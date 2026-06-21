"""LinkedIn lead source (optional) — industry/keyword search.

Backed by the open-source **linkedin-api** (https://github.com/tomquirk/linkedin-api),
which searches LinkedIn by keyword and returns companies/people — a natural fit
for "type an industry, get leads". Mirrors the gosom integration: it returns
records in the same shape the scraper maps to leads.

Off by default (LINKEDIN_ENABLED=false); when disabled or misconfigured it
raises a clear error instead of returning data.

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
    if not settings.LINKEDIN_ENABLED:
        return False
    return bool(settings.LINKEDIN_COOKIE or (settings.LINKEDIN_USER and settings.LINKEDIN_PASS))


def test_connection() -> dict:
    """Verify LinkedIn credentials before a full scrape. {ok, message}."""
    if not settings.LINKEDIN_ENABLED:
        return {"ok": False, "message": "LinkedIn is disabled. Set LINKEDIN_ENABLED=true in .env."}
    if not (settings.LINKEDIN_COOKIE or (settings.LINKEDIN_USER and settings.LINKEDIN_PASS)):
        return {"ok": False, "message": "Add LINKEDIN_USER/LINKEDIN_PASS or LINKEDIN_COOKIE in .env."}
    try:
        global _client
        _client = None  # force a fresh login for the test
        _get_client()
        return {"ok": True, "message": f"Connected to LinkedIn as {settings.LINKEDIN_USER}."}
    except ModuleNotFoundError:
        return {"ok": False, "message": "linkedin-api not installed. Run: uv pip install linkedin-api"}
    except Exception as exc:
        return {"ok": False, "message": f"Login failed: {type(exc).__name__}: {exc}"[:200]}


def _get_client():
    global _client
    if _client is not None:
        return _client
    from linkedin_api import Linkedin  # lazy import — optional dependency

    if settings.LINKEDIN_COOKIE:
        # Cookie auth — far more reliable than password for fresh accounts.
        import requests

        jar = requests.cookies.RequestsCookieJar()
        jar.set("li_at", settings.LINKEDIN_COOKIE, domain=".www.linkedin.com")
        if settings.LINKEDIN_JSESSIONID:
            jar.set("JSESSIONID", settings.LINKEDIN_JSESSIONID, domain=".www.linkedin.com")
        _client = Linkedin(
            settings.LINKEDIN_USER or "", settings.LINKEDIN_PASS or "",
            cookies=jar, authenticate=True,
        )
    else:
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
    """Return real LinkedIn lead records. Raises if the source isn't configured."""
    if not settings.LINKEDIN_ENABLED:
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
