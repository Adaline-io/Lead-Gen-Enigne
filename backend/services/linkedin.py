"""LinkedIn lead source (optional).

Recommended open-source backend: **StaffSpy** (https://github.com/cullenwatson/StaffSpy)
— a maintained LinkedIn company/employee scraper, the closest analogue to gosom
for LinkedIn. (Alternatives: tomquirk/linkedin-api, speedyapply/JobSpy.)

This module mirrors the gosom integration: it returns records in the same shape
the scraper maps to leads. It is **off by default** (LINKEDIN_ENABLED=false) and
falls back to clearly-labelled demo data so the UI flow works locally without
credentials.

⚠ Scraping LinkedIn may violate its Terms of Service and can get accounts
restricted. Use a dedicated account, keep volumes low, and confirm this is
acceptable for your use before enabling.
"""

from __future__ import annotations

from backend.config import settings


def _demo_records(query: str, city: str | None) -> list[dict]:
    """Sample LinkedIn-style results (people at companies) for local testing."""
    import random

    rng = random.Random(hash(("li", query, city)) & 0xFFFFFFFF)
    place = (city or "Dubai").strip()
    base = (query or "Business").strip().title()
    first = ["Aisha", "Omar", "Layla", "Khalid", "Sara", "Yusuf", "Mona", "Tariq"]
    roles = ["Founder", "Managing Director", "Head of Marketing", "CEO",
             "Operations Manager", "Business Development Lead"]
    out: list[dict] = []
    for i in range(rng.randint(5, 8)):
        person = f"{rng.choice(first)} {chr(65 + i)}."
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
            "contact_name": person,
        })
    return out


def _staffspy_records(query: str, city: str | None, limit: int) -> list[dict]:
    """Real LinkedIn scrape via StaffSpy. Lazy import so it's an optional dep.

    Install with:  uv pip install staffspy   (then set LINKEDIN_ENABLED=true)
    First run opens a browser login that caches a session to
    LINKEDIN_SESSION_FILE.
    """
    from staffspy import LinkedInAccount  # type: ignore

    account = LinkedInAccount(session_file=settings.LINKEDIN_SESSION_FILE)
    df = account.scrape_staff(search_term=query, location=city or "", max_results=limit or 50)

    records: list[dict] = []
    for row in df.to_dict("records"):
        records.append({
            "title": row.get("company") or row.get("name") or query,
            "category": row.get("position") or row.get("headline"),
            "address": row.get("location") or city,
            "city": row.get("location") or city,
            "website": row.get("profile_link") or row.get("company_url"),
            "emails": [row["email"]] if row.get("email") else [],
            "phone": None,
            "review_rating": None,
            "review_count": None,
            "contact_name": row.get("name"),
        })
    return records


def run_linkedin(query: str, city: str | None, limit: int | None = None) -> list[dict]:
    """Return LinkedIn lead records (or demo data when not configured)."""
    if not settings.LINKEDIN_ENABLED:
        if settings.SCRAPER_DEMO:
            return _demo_records(query, city)
        raise RuntimeError(
            "LinkedIn source is disabled. Set LINKEDIN_ENABLED=true and install "
            "staffspy (uv pip install staffspy) to enable it."
        )
    try:
        return _staffspy_records(query, city, limit or 50)
    except ModuleNotFoundError:
        raise RuntimeError(
            "staffspy is not installed. Run: uv pip install staffspy"
        )
