"""Deterministic, data-driven lead quality scoring (0.0–10.0).

This mirrors the vertical rubrics in the Claude prompts (backend/prompts/*),
but computes a score purely from a lead's own scraped fields — rating, review
count, website/TLD, location signals, business-name signals and country. It is
the baseline qualifier: every lead gets an explainable score and a
``qualified`` flag even when the Anthropic API is unavailable, and manually
added leads are scored on the spot.

``qualified`` is True when ``score >= 5.0`` (same threshold the prompts use).
"""

from __future__ import annotations

from backend.models import Lead

ScoreResult = tuple[float, bool, str]

GCC_COUNTRIES = {
    "UAE", "KSA", "SAUDI ARABIA", "QATAR", "BAHRAIN", "OMAN", "KUWAIT",
}
GULF_TLDS = (".ae", ".sa", ".qa", ".bh", ".kw", ".om")

# Premium retail districts that signal a brand-class abaya business.
ABAYA_PREMIUM = (
    "marina", "downtown", "jbr", "city walk", "mall of the emirates",
    "al wahda", "al majaz", "sahara", "khalidiya", "marina mall", "yas mall",
    "olaya", "tahlia", "king fahd", "andalus", "pearl", "lusail", "west bay",
)
# Commodity / wholesale tokens that drag an abaya lead down.
ABAYA_NEGATIVE = (
    "trading", "wholesale", "general stores", "general trading",
    "cash & carry", "cash and carry", "kiosk", "souk",
)

# Industrial / trade zones that signal a B2B auto-parts distributor.
AUTOPARTS_ZONES = (
    "industrial", "jebel ali", "free zone", "al quoz", "sulay", "al khumra",
    "al jubail", "2nd industrial", "3rd industrial", "1st industrial",
)
# Distribution / wholesale name signals (positive).
AUTOPARTS_POSITIVE = (
    "wholesale", "distribut", "oem", "supplier", "spare parts", "trading",
    "parts & accessories", "parts and accessories",
)
# Pure-retail / wrong-fit signals (these BUY from distributors).
AUTOPARTS_NEGATIVE = (
    "garage", "service center", "service centre", "tyre", "tire",
    "car wash", "oil change", "lube",
)


def _has(text: str, needles) -> bool:
    return any(n in text for n in needles)


def _website_signal(website: str | None) -> tuple[float, bool]:
    """Return (points, is_gulf_tld). 0 points if no website."""
    if not website:
        return 0.0, False
    low = website.lower()
    gulf = any(low.split("?")[0].rstrip("/").endswith(t) or t + "/" in low for t in GULF_TLDS)
    return (2.0 if gulf else 1.5), gulf


def _clamp(score: float) -> float:
    return round(max(0.0, min(10.0, score)), 1)


def _score_abaya(lead: Lead, loc: str, name: str, country: str) -> ScoreResult:
    s = 0.0
    bits: list[str] = []
    rating = lead.rating or 0.0
    reviews = lead.review_count or 0

    if rating >= 4.5:
        s += 3.5
    elif rating >= 4.0:
        s += 2.0
    elif rating > 0:
        s += 0.5
    if rating and rating < 4.0 and reviews > 20:
        s -= 1.5  # real poor-service signal
        bits.append(f"{rating}★ poor")
    elif rating:
        bits.append(f"{rating}★")

    if reviews >= 100:
        s += 2.5
    elif reviews >= 50:
        s += 1.5
    elif reviews >= 20:
        s += 0.5
    if reviews:
        bits.append(f"{reviews} reviews")

    wpts, gulf = _website_signal(lead.website)
    s += wpts
    bits.append("gulf site" if gulf else ("site" if wpts else "no site"))

    if _has(loc, ABAYA_PREMIUM):
        s += 2.0
        bits.append("premium district")

    if country in GCC_COUNTRIES:
        s += 1.0
    elif country:
        s -= 3.0  # we serve the GCC abaya market

    if _has(name, ABAYA_NEGATIVE):
        s -= 2.5
        bits.append("commodity name")

    score = _clamp(s)
    return score, score >= 5.0, _reason(bits)


def _score_autoparts(lead: Lead, loc: str, name: str, country: str) -> ScoreResult:
    s = 0.0
    bits: list[str] = []
    rating = lead.rating or 0.0
    reviews = lead.review_count or 0

    if _has(name, AUTOPARTS_POSITIVE):
        s += 3.0
        bits.append("wholesale/distribution name")
    if _has(loc, AUTOPARTS_ZONES):
        s += 2.5
        bits.append("industrial zone")

    wpts, _ = _website_signal(lead.website)
    s += wpts
    bits.append("site" if wpts else "no site")

    if reviews >= 100:
        s += 2.0
    elif reviews >= 50:
        s += 1.5
    if reviews:
        bits.append(f"{reviews} reviews")
    if rating >= 4.5:
        s += 1.5
    elif rating >= 4.0:
        s += 0.8

    if _has(name, AUTOPARTS_NEGATIVE) or _has(loc, AUTOPARTS_NEGATIVE):
        s -= 3.5
        bits.append("retail/service — wrong fit")

    if country in {"KSA", "SAUDI ARABIA", "UAE"}:
        s += 1.0
    elif country:
        s -= 1.5

    score = _clamp(s)
    return score, score >= 5.0, _reason(bits)


def _score_default(lead: Lead, loc: str, name: str, country: str) -> ScoreResult:
    s = 0.0
    bits: list[str] = []
    rating = lead.rating or 0.0
    reviews = lead.review_count or 0

    if rating >= 4.5:
        s += 3.5
    elif rating >= 4.0:
        s += 2.0
    elif rating:
        s += 0.5
    if rating:
        bits.append(f"{rating}★")

    if reviews >= 100:
        s += 3.0
    elif reviews >= 50:
        s += 2.0
    elif reviews >= 20:
        s += 1.0
    if reviews:
        bits.append(f"{reviews} reviews")

    wpts, _ = _website_signal(lead.website)
    s += wpts
    bits.append("site" if wpts else "no site")

    in_region = country in GCC_COUNTRIES or "kerala" in loc or "calicut" in loc or country == "INDIA"
    if in_region:
        s += 1.5

    score = _clamp(s)
    return score, score >= 5.0, _reason(bits)


def _reason(bits: list[str]) -> str:
    """One-line summary of the actual data signals — no region tag, no tier
    label (the score number already conveys the qualification)."""
    return (", ".join(b for b in bits if b) or "no strong signals")[:160]


def compute_quality(lead: Lead) -> ScoreResult:
    """Score a lead 0–10 from its own data. Returns (score, qualified, reason).

    Location signals (premium districts, industrial zones, region) are matched
    against the address/city; name signals (brand vs commodity, wholesale vs
    retail) are matched against the business name — so the two never bleed.
    """
    loc = " ".join((lead.address or "", lead.city or "", lead.category or "")).lower()
    name = (lead.name or "").lower()
    country = (lead.country or "").strip().upper()

    match lead.vertical_tag:
        case "abaya":
            return _score_abaya(lead, loc, name, country)
        case "autoparts_b2b":
            return _score_autoparts(lead, loc, name, country)
        case _:
            return _score_default(lead, loc, name, country)
