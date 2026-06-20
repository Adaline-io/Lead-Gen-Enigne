"""gosom Google Maps scraper integration + background job orchestration.

The public entry point is ``run_scrape_job(job_id)`` — designed to run inside a
FastAPI ``BackgroundTasks`` callback. It opens its own DB session, drives the
gosom subprocess, dedupes + inserts leads, hands each to the scorer, and keeps
the ``jobs`` row updated through the queued → running → scoring → done states.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.config import settings
from backend.db import SessionLocal
from backend.models import Job, Lead
from backend.services.scorer import score_lead
from backend.services.whatsapp import whatsapp_url

# Crude country detection from free-text address.
_COUNTRY_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("united arab emirates", "uae", "dubai", "sharjah", "abu dhabi", "ajman"), "UAE"),
    (("saudi", "ksa", "riyadh", "jeddah", "dammam", "mecca", "medina"), "KSA"),
    (("qatar", "doha"), "Qatar"),
    (("bahrain", "manama"), "Bahrain"),
    (("oman", "muscat"), "Oman"),
    (("kuwait",), "Kuwait"),
    (("india", "kerala", "calicut", "kozhikode", "kochi", "bangalore"), "India"),
]


def gosom_live() -> bool:
    """True when the gosom binary is present (else demo/unavailable)."""
    import os

    return os.path.exists(settings.GOSOM_BIN)


def detect_country(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for needles, country in _COUNTRY_HINTS:
        if any(n in low for n in needles):
            return country
    return None


def _first_email(value) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str) and value:
        return value.split(",")[0].strip()
    return None


def map_record(rec: dict, job: Job) -> dict:
    """Map a single gosom JSON record to Lead field kwargs."""
    complete = rec.get("complete_address")
    city = job.city
    country = None
    if isinstance(complete, dict):
        city = complete.get("city") or city
        country = complete.get("country")

    address = rec.get("address") or rec.get("complete_address")
    if isinstance(address, dict):
        address = ", ".join(str(v) for v in address.values() if v)

    country = country or detect_country(address) or detect_country(rec.get("title"))

    fields = {
        "name": rec.get("title") or rec.get("name") or "(unknown)",
        "category": rec.get("category"),
        "address": address,
        "city": city,
        "country": country,
        "phone": rec.get("phone"),
        "email": _first_email(rec.get("emails") or rec.get("email")),
        "website": rec.get("website") or rec.get("web_site"),
        "rating": rec.get("review_rating") or rec.get("rating"),
        "review_count": rec.get("review_count"),
    }
    # LinkedIn results carry a decision-maker name — keep it as a note.
    if rec.get("contact_name"):
        fields["notes"] = f"Contact: {rec['contact_name']}"
    return fields


def build_search_line(query: str, city: str | None) -> str:
    """The single search line gosom consumes — fold location into the query."""
    line = query.strip()
    if city and city.lower() not in line.lower():
        line = f"{line} {city}".strip()
    return line


def _zoom_for_radius(radius_m: int | None) -> int | None:
    if not radius_m:
        return None
    km = radius_m / 1000
    if km <= 2:
        return 15
    if km <= 5:
        return 14
    if km <= 10:
        return 13
    if km <= 25:
        return 12
    return 11


def run_gosom(
    queries: list[str],
    depth: int,
    *,
    city: str | None = None,
    radius_m: int | None = None,
    lat: float | None = None,
    lng: float | None = None,
    lang: str | None = None,
    extract_emails: bool = False,
) -> list[dict]:
    """Invoke the gosom binary over one or more queries and return JSON records.

    Raises FileNotFoundError if the binary is missing, TimeoutError on timeout.
    """
    if isinstance(queries, str):
        queries = [queries]
    out_dir = Path(settings.SCRAPE_OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"scrape_{stamp}.json"

    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as qf:
        for q in queries:
            qf.write(build_search_line(q, city) + "\n")
        query_file = qf.name

    cmd = [
        settings.GOSOM_BIN,
        "-input",
        query_file,
        "-results",
        str(out_path),
        "-depth",
        str(depth),
        "-exit-on-inactivity",
        "3m",
        "-json",
    ]
    if extract_emails:
        cmd.append("-email")
    if lang:
        cmd += ["-lang", lang]
    # Anchor the search on real coordinates so the radius actually means
    # something (gosom's -radius only bites when paired with -geo).
    if lat is not None and lng is not None:
        cmd += ["-geo", f"{lat},{lng}"]
        zoom = _zoom_for_radius(radius_m)
        if zoom:
            cmd += ["-zoom", str(zoom)]
    if radius_m:
        cmd += ["-radius", str(radius_m)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.SCRAPE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        # gosom isn't installed. In demo mode, return sample results so the
        # whole find → review → approve flow works locally without it.
        if settings.SCRAPER_DEMO:
            return demo_records(queries[0] if queries else "", city)
        raise
    if proc.returncode != 0 and not out_path.exists():
        raise RuntimeError(
            f"gosom exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        )

    if not out_path.exists():
        return []
    return parse_output(out_path)


def demo_records(query: str, city: str | None) -> list[dict]:
    """Sample 'scrape' results for local testing without the gosom binary.

    Produces a realistic spread (premium → weak) so scoring varies. Clearly
    labelled in the address so they're easy to spot and clean up.
    """
    import random

    rng = random.Random(hash((query, city)) & 0xFFFFFFFF)
    place = (city or "Dubai").strip()
    base = (query or "Business").strip().title()
    suffixes = ["House", "Atelier", "Boutique", "Trading Co", "Hub", "Center", "Studio", "Group"]
    out: list[dict] = []
    for i in range(rng.randint(5, 8)):
        rating = round(rng.uniform(3.4, 4.9), 1)
        reviews = rng.choice([8, 24, 47, 60, 95, 130, 240, 410])
        has_site = rng.random() > 0.35
        # Distinct suffix per row so dedup doesn't collapse the batch.
        name = f"{base.split()[0]} {suffixes[i % len(suffixes)]} {place}"
        out.append({
            "title": name,
            "category": base,
            "address": f"{place} — sample lead (demo scrape)",
            "city": place,
            "phone": f"+9715{rng.randint(10000000, 99999999)}",
            "website": f"https://{base.split()[0].lower()}{i}.example.com" if has_site else None,
            "review_rating": rating,
            "review_count": reviews,
            "emails": [f"hello@{base.split()[0].lower()}{i}.example.com"] if has_site else [],
        })
    return out


def parse_output(path: Path) -> list[dict]:
    """gosom may emit a JSON array or newline-delimited JSON objects."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        records = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records


def _insert_leads(db, records: list[dict], job: Job) -> list[Lead]:
    """Insert deduped leads (status=pending). Returns the newly inserted rows."""
    from backend.services.intake import find_duplicate, known_client_flag

    inserted: list[Lead] = []
    for rec in records:
        fields = map_record(rec, job)

        if find_duplicate(
            db,
            name=fields["name"],
            phone=fields.get("phone"),
            city=fields.get("city"),
            website=fields.get("website"),
        ) is not None:
            continue  # already have this business

        lead = Lead(
            **fields,
            vertical_tag=job.vertical_tag,
            query_used=job.query,
            status="pending",
            scraped_at=datetime.now(timezone.utc),
        )
        # Existing-client guard.
        flag = known_client_flag(lead.name)
        if flag:
            lead.score_flagged = True
            lead.flag_reason = flag

        db.add(lead)
        try:
            db.flush()
        except Exception:
            db.rollback()
            continue
        inserted.append(lead)
    db.commit()
    return inserted


def run_scrape_job(job_id: int) -> None:
    """Background entry point: scrape → insert → score → done."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        # The actual search terms (expansion of the typed industry).
        terms = [job.query]
        if job.queries:
            try:
                parsed = json.loads(job.queries)
                if isinstance(parsed, list) and parsed:
                    terms = [str(t) for t in parsed]
            except json.JSONDecodeError:
                pass

        try:
            if job.source == "linkedin":
                from backend.services.linkedin import run_linkedin

                records = []
                for term in terms:
                    records += run_linkedin(term, job.city, job.max_results)
            else:
                records = run_gosom(
                    terms,
                    job.depth,
                    city=job.city,
                    radius_m=job.radius_m,
                    lat=job.lat,
                    lng=job.lng,
                    lang=job.lang,
                    extract_emails=job.extract_emails,
                )
            if job.max_results:
                records = records[: job.max_results]
        except FileNotFoundError:
            job.status = "failed"
            job.error_message = (
                f"gosom binary not found at {settings.GOSOM_BIN!r}. "
                "Install gosom and set GOSOM_BIN."
            )
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        except (subprocess.TimeoutExpired, TimeoutError):
            job.status = "failed"
            job.error_message = "gosom timed out"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return
        except Exception as exc:
            job.status = "failed"
            job.error_message = f"{type(exc).__name__}: {exc}"[:300]
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        leads = _insert_leads(db, records, job)
        job.leads_found = len(leads)
        job.status = "scoring"
        db.commit()

        scored = 0
        for lead in leads:
            score, qualified, reason = score_lead(lead)
            lead.score = score
            lead.qualified = qualified
            lead.ai_reason = reason
            lead.scored_at = datetime.now(timezone.utc)
            lead.whatsapp_url = whatsapp_url(
                lead.phone, lead.country, lead.name, lead.city, lead.vertical_tag
            )
            scored += 1
            job.leads_scored = scored
            db.commit()

        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
