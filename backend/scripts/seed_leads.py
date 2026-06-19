"""Seed ~30 fake leads across mixed verticals and statuses for frontend dev.

Run with::

    uv run python -m backend.scripts.seed_leads
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from backend.scripts.seed_users import _ensure_session_secret  # noqa: E402

_ensure_session_secret()

from backend.db import SessionLocal, create_all  # noqa: E402
from backend.models import Lead, User  # noqa: E402
from backend.services.whatsapp import whatsapp_url  # noqa: E402

ABAYA = [
    ("Hessa Boutique", "Dubai", "UAE", 4.8, 240, "https://hessa.ae"),
    ("Al Noor Abaya Atelier", "Sharjah", "UAE", 4.6, 160, "https://alnoor.ae"),
    ("Modanisa Atelier", "Riyadh", "KSA", 4.7, 320, "https://modanisa.sa"),
    ("Silk Road Abayas", "Doha", "Qatar", 4.3, 80, "https://silkroad.qa"),
    ("Layali Couture", "Abu Dhabi", "UAE", 4.9, 410, "https://layali.ae"),
    ("Karama Fashion Wholesale", "Dubai", "UAE", 3.6, 45, None),
    ("Jeddah Modest Wear", "Jeddah", "KSA", 4.1, 55, "https://jmw.sa"),
    ("Pearl Abaya House", "Doha", "Qatar", 4.5, 130, "https://pearlabaya.qa"),
    ("Al Wahda General Trading", "Sharjah", "UAE", 3.2, 28, None),
    ("Nadia's Modest Boutique", "Kuwait City", "Kuwait", 4.4, 90, "https://nadia.kw"),
]

AUTOPARTS = [
    ("Gulf Spare Parts Wholesale", "Riyadh", "KSA", 4.5, 110, "https://gulfparts.sa"),
    ("Al Quoz Auto Distributors", "Dubai", "UAE", 4.6, 95, "https://alquozauto.ae"),
    ("Dammam OEM Supplier Co", "Dammam", "KSA", 4.7, 140, "https://dammamoem.sa"),
    ("Jebel Ali Parts Trading", "Dubai", "UAE", 4.4, 70, "https://japt.ae"),
    ("Sharjah Industrial Auto", "Sharjah", "UAE", 4.2, 60, "https://siauto.ae"),
    ("Quick Lube Car Wash", "Dubai", "UAE", 3.9, 200, None),
    ("Speedy Tyre Shop", "Riyadh", "KSA", 3.7, 150, None),
    ("Al Khumra Parts Distributor", "Jeddah", "KSA", 4.6, 88, "https://alkhumra.sa"),
    ("Downtown Auto Garage", "Abu Dhabi", "UAE", 4.0, 75, None),
    ("Sulay Industrial Spares", "Riyadh", "KSA", 4.8, 175, "https://sulayspares.sa"),
]

FUEL = [
    ("Roca Fuels MRPL Station", "Calicut", "India", 4.6, 320, "https://rocafuels.in"),
    ("Highway Fuel Point", "Kochi", "India", 4.1, 90, None),
    ("Malabar Petro Stop", "Calicut", "India", 4.3, 110, "https://malabarpetro.in"),
]

HOSPITALITY = [
    ("The Backwater Retreat", "Alleppey", "India", 4.8, 520, "https://backwater.in"),
    ("Calicut Heritage Stay", "Calicut", "India", 4.5, 180, "https://heritage.in"),
    ("Marina Boutique Hotel", "Kochi", "India", 4.4, 240, "https://marinahotel.in"),
    ("Hilltop Bungalow Resort", "Wayanad", "India", 4.7, 300, "https://hilltop.in"),
]

STATUSES = [
    "pending",
    "new",
    "new",
    "contacted",
    "contacted",
    "replied",
    "meeting",
    "won",
    "lost_no_response",
    "lost_poor_fit",
]


def _score_for(rating: float, reviews: int, website: str | None) -> tuple[float, bool, str]:
    score = 0.0
    if rating >= 4.5:
        score += 4.0
    elif rating >= 4.0:
        score += 2.5
    else:
        score += 1.0
    if reviews >= 100:
        score += 3.0
    elif reviews >= 50:
        score += 1.5
    if website:
        score += 2.0
    score = min(round(score, 1), 10.0)
    qualified = score >= 5.0
    reason = (
        f"{'Strong' if qualified else 'Weak'} signals — "
        f"{rating}★, {reviews} reviews, {'site' if website else 'no site'}"
    )[:160]
    return score, qualified, reason


def seed() -> None:
    create_all()
    db = SessionLocal()
    rng = random.Random(42)
    try:
        sales_ids = [
            u.id
            for u in db.query(User).filter(User.role.in_(("sales", "admin"))).all()
        ]
        if not sales_ids:
            sales_ids = [None]

        datasets = [
            ("abaya", ABAYA),
            ("autoparts_b2b", AUTOPARTS),
            ("fuel", FUEL),
            ("hospitality", HOSPITALITY),
        ]

        created = 0
        for vertical, rows in datasets:
            for name, city, country, rating, reviews, website in rows:
                if db.query(Lead).filter(Lead.name == name).first():
                    continue
                status = STATUSES[created % len(STATUSES)]
                score, qualified, reason = _score_for(rating, reviews, website)
                phone = f"+9715{rng.randint(10000000, 99999999)}"
                lead = Lead(
                    name=name,
                    city=city,
                    country=country,
                    category={
                        "abaya": "Clothing store",
                        "autoparts_b2b": "Auto parts store",
                        "fuel": "Gas station",
                        "hospitality": "Hotel",
                    }[vertical],
                    address=f"{city}, {country}",
                    phone=phone,
                    email=None,
                    website=website,
                    rating=rating,
                    review_count=reviews,
                    vertical_tag=vertical,
                    query_used=f"{vertical} {city}",
                    score=score,
                    qualified=qualified,
                    ai_reason=reason,
                    scored_at=datetime.now(timezone.utc),
                    status=status,
                    assigned_to=(
                        None
                        if status == "pending"
                        else rng.choice(sales_ids)
                    ),
                    scraped_at=datetime.now(timezone.utc) - timedelta(days=created),
                )
                lead.whatsapp_url = whatsapp_url(
                    lead.phone, lead.country, lead.name, lead.city, lead.vertical_tag
                )
                db.add(lead)
                created += 1
        db.commit()
        print(f"Seeded {created} leads across {len(datasets)} verticals.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
