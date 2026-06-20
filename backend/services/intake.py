"""Lead intake helpers shared by scrape, CSV import and manual add.

Keeps the "just works" behaviours in one place: fuzzy de-duplication, the
existing-client guard, round-robin assignment, and the follow-up-due rule.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models import Lead, User

# A lead is "follow-up due" once it has sat this long in an active,
# awaiting-reply stage without a fresh contact.
FOLLOWUP_DAYS = 3
FOLLOWUP_STATUSES = ("contacted", "replied", "meeting")

# Live clients — never pitch an existing customer. Substring match on name.
KNOWN_CLIENTS = ("alifa", "roca")


def normalize_name(name: str | None) -> str:
    """Lowercase, drop punctuation and common company suffixes, collapse space."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    s = re.sub(
        r"\b(llc|wll|est|co|company|trading|general|stores?|group|the)\b", " ", s
    )
    return re.sub(r"\s+", " ", s).strip()


def _domain(url: str | None) -> str:
    if not url:
        return ""
    u = url.lower().split("//")[-1]
    return u.split("/")[0].lstrip("www.").strip()


def find_duplicate(
    db: Session,
    *,
    name: str,
    phone: str | None,
    city: str | None,
    website: str | None,
) -> Lead | None:
    """Return an existing lead that is very likely the same business, or None.

    Matches on: same phone, OR same normalized name in the same city, OR the
    same website domain.
    """
    if phone:
        hit = db.scalar(select(Lead).where(Lead.phone == phone))
        if hit:
            return hit

    norm = normalize_name(name)
    dom = _domain(website)

    candidates = db.scalars(
        select(Lead).where(
            or_(
                Lead.city == city if city else False,
                Lead.website.ilike(f"%{dom}%") if dom else False,
            )
        )
    ).all()
    for lead in candidates:
        if dom and _domain(lead.website) == dom:
            return lead
        if norm and normalize_name(lead.name) == norm and (lead.city or "") == (city or ""):
            return lead
    return None


# Free-typed industry text -> the best-fit scoring rubric. Anything we don't
# recognise scores with the universal "default" rubric.
_VERTICAL_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("abaya", "modest", "fashion", "boutique", "clothing", "apparel", "couture"), "abaya"),
    (("auto part", "spare part", "car part", "auto spare", "automotive", "oem", "tyre", "tire", "parts wholesale", "parts distributor"), "autoparts_b2b"),
    (("fuel", "petrol", "gas station", "filling station", "petroleum", "diesel"), "fuel"),
    (("hotel", "resort", "hospitality", "restaurant", "cafe", "guest house", "spa", "lodge"), "hospitality"),
]


def infer_vertical(text: str | None) -> str:
    low = (text or "").lower()
    for needles, tag in _VERTICAL_HINTS:
        if any(n in low for n in needles):
            return tag
    return "default"


def known_client_flag(name: str | None) -> str | None:
    low = (name or "").lower()
    for client in KNOWN_CLIENTS:
        if client in low:
            return f"Possible existing client ({client.upper()}) — verify before outreach"
    return None


def pick_round_robin(db: Session) -> int | None:
    """Return the sales/admin user id carrying the fewest active leads."""
    reps = db.scalars(
        select(User).where(User.role.in_(("sales", "admin")))
    ).all()
    if not reps:
        return None
    counts = dict(
        db.execute(
            select(Lead.assigned_to, func.count(Lead.id))
            .where(Lead.archived.is_(False))
            .group_by(Lead.assigned_to)
        ).all()
    )
    return min(reps, key=lambda u: counts.get(u.id, 0)).id


def followup_cutoff(now: datetime | None = None) -> datetime:
    # Naive UTC, to match the datetimes SQLite stores (no tzinfo).
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return now - timedelta(days=FOLLOWUP_DAYS)
