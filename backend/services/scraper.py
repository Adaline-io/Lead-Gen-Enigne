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


_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday"]


def _summarise_hours(open_hours) -> tuple[str | None, dict | None]:
    """Return a one-line opening-hours summary + the raw per-day dict.

    gosom's ``open_hours`` is like {"Monday":["10 am–10:30 pm"], ...}. We keep
    the structured dict (for 'today's hours') and a compact human summary.
    """
    if isinstance(open_hours, str) and open_hours.strip():
        try:
            open_hours = json.loads(open_hours)
        except json.JSONDecodeError:
            return open_hours.strip()[:200], None
    if not isinstance(open_hours, dict) or not open_hours:
        return None, None
    parts = []
    for day in _DAY_ORDER:
        slots = open_hours.get(day)
        if slots:
            txt = ", ".join(slots) if isinstance(slots, list) else str(slots)
            parts.append(f"{day[:3]} {txt}")
    summary = " · ".join(parts) if parts else None
    return (summary[:300] if summary else None), open_hours


def build_enrichment(rec: dict) -> dict:
    """Pull the cold-call-useful extras out of a raw gosom record."""
    enr: dict = {}

    maps_url = rec.get("link") or rec.get("url")
    if maps_url:
        enr["maps_url"] = maps_url

    hours_summary, hours_raw = _summarise_hours(rec.get("open_hours"))
    if hours_summary:
        enr["hours"] = hours_summary
    if hours_raw:
        enr["hours_by_day"] = hours_raw

    owner = rec.get("owner")
    if isinstance(owner, str) and owner.strip():
        # gosom's CSV gives owner as a JSON string; JSON mode gives a dict.
        try:
            owner = json.loads(owner)
        except json.JSONDecodeError:
            pass
    if isinstance(owner, dict) and owner.get("name"):
        enr["owner"] = owner["name"]
    elif isinstance(owner, str) and owner.strip():
        enr["owner"] = owner.strip()
    if rec.get("contact_name"):
        enr["owner"] = enr.get("owner") or rec["contact_name"]

    for key in ("price_range", "plus_code", "status"):
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            enr[key] = val.strip()

    lat, lng = rec.get("latitude"), rec.get("longitude")
    if lat and lng:
        enr["lat"], enr["lng"] = lat, lng
        enr.setdefault("maps_url", f"https://www.google.com/maps?q={lat},{lng}")

    return enr


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

    # Stash the cold-call extras (hours, owner, maps link, price) as JSON.
    enrichment = build_enrichment(rec)
    if enrichment:
        fields["enrichment"] = json.dumps(enrichment)
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
    keywords: str | None = None,
) -> list[dict]:
    """Invoke the gosom binary over one or more queries and return JSON records.

    Raises FileNotFoundError if the binary is missing, TimeoutError on timeout.
    gosom always runs on the clean query; keyword narrowing is done by
    ``filter_by_keywords`` on the results, never folded into the search itself.
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
        settings.GOSOM_INACTIVITY,
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

    log_path = out_path.with_suffix(".log")
    print(f"[scrape] running gosom: {' '.join(cmd)}", flush=True)
    print(f"[scrape] gosom output → {log_path}  (tail -f to watch)", flush=True)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.SCRAPE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        # gosom isn't installed — fail loudly so the job surfaces a clear error
        # ("install gosom and set GOSOM_BIN") rather than inventing fake leads.
        raise
    except subprocess.TimeoutExpired as exc:
        # Persist whatever gosom emitted before we killed it, then surface it.
        _write_gosom_log(log_path, cmd, exc.stdout, exc.stderr)
        print(
            f"[scrape] gosom TIMED OUT after {settings.SCRAPE_TIMEOUT_SECONDS}s "
            f"— see {log_path}",
            flush=True,
        )
        raise

    _write_gosom_log(log_path, cmd, proc.stdout, proc.stderr)
    tail = (proc.stderr or proc.stdout or "").strip()
    print(
        f"[scrape] gosom exited {proc.returncode}; "
        f"results file exists: {out_path.exists()}",
        flush=True,
    )
    if tail:
        print(f"[scrape] gosom said: {tail[-800:]}", flush=True)

    if proc.returncode != 0 and not out_path.exists():
        raise RuntimeError(
            f"gosom exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
        )

    if not out_path.exists():
        return []
    return parse_output(out_path)


def _write_gosom_log(
    path: Path, cmd: list[str], out: str | None, err: str | None
) -> None:
    """Persist the exact gosom command + its output so a stuck/empty run is
    debuggable after the fact. Best-effort — never raises."""
    try:
        path.write_text(
            "CMD: " + " ".join(cmd) + "\n\n"
            "--- STDOUT ---\n" + (out or "") + "\n\n"
            "--- STDERR ---\n" + (err or ""),
            encoding="utf-8",
        )
    except Exception:
        pass


def has_useful_data(rec: dict) -> bool:
    """True if a scraped row carries real, actionable contact data.

    gosom returns everything Google Maps lists — including empty/placeholder
    rows with just a name. We keep every real lead but drop those junk rows:
    a lead is useful only if it has at least one of phone, email, website, or
    a real address (the data a rep actually needs to reach out).
    """
    phone = rec.get("phone")
    email = rec.get("emails") or rec.get("email")
    website = rec.get("website") or rec.get("web_site")
    address = rec.get("address") or rec.get("complete_address")
    return bool(
        (isinstance(phone, str) and phone.strip())
        or email
        or (isinstance(website, str) and website.strip())
        or address
    )


def keep_useful(records: list[dict]) -> list[dict]:
    """Drop junk rows with no contact data; keep all real leads gosom found."""
    return [r for r in records if has_useful_data(r)]


def _keyword_tokens(keywords: str | None) -> list[str]:
    """Split a keywords string into lowercase tokens (comma- or space-separated)."""
    if not keywords:
        return []
    raw = keywords.replace(",", " ").split()
    return [t.lower() for t in raw if t.strip()]


def filter_by_keywords(records: list[dict], keywords: str | None) -> list[dict]:
    """Keep only scraped rows that match ANY keyword (post-scrape filtering).

    gosom returns everything Google Maps has for the industry; the keywords
    then narrow that data sheet down to what the rep actually wants (e.g.
    'premium', 'wholesale'). Matches across name, category, address and website.
    No keywords → everything passes through unchanged.
    """
    tokens = _keyword_tokens(keywords)
    if not tokens:
        return records
    kept: list[dict] = []
    for rec in records:
        hay = " ".join(
            str(rec.get(k) or "")
            for k in ("title", "name", "category", "categories", "address", "website")
        ).lower()
        if any(tok in hay for tok in tokens):
            kept.append(rec)
    return kept


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
                import time

                from backend.services.linkedin import run_linkedin

                records = []
                for i, term in enumerate(terms):
                    if i > 0 and settings.LINKEDIN_THROTTLE_SECONDS:
                        time.sleep(settings.LINKEDIN_THROTTLE_SECONDS)  # be polite
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
                    keywords=job.keywords,
                )
            # Keep EVERY business gosom returns — including sparse ones with no
            # phone/site yet — so the team can see all located businesses and
            # fill in missing details by hand to lift the score. The only
            # narrowing is the rep's optional keywords (skipped when blank).
            raw_count = len(records)
            with_contact = sum(1 for r in records if has_useful_data(r))
            records = filter_by_keywords(records, job.keywords)
            kw_count = len(records)
            if job.max_results:
                records = records[: job.max_results]
            # Funnel so a small batch is diagnosable: where did rows drop?
            print(
                f"[scrape] job {job.id} funnel: gosom={raw_count} "
                f"(with-contact={with_contact}, kept all) → "
                f"keywords({job.keywords or 'none'})={kw_count} → "
                f"max({job.max_results or 'none'})={len(records)}",
                flush=True,
            )
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

        try:
            found = len(records)
            leads = _insert_leads(db, records, job)
            job.leads_found = len(leads)
            # gosom may return businesses we already have; we dedupe them rather
            # than re-adding. Record how many so the UI can explain a small batch.
            job.leads_duplicate = max(0, found - len(leads))
            print(
                f"[scrape] job {job.id} insert: {len(leads)} new · "
                f"{job.leads_duplicate} duplicates of leads already in the DB",
                flush=True,
            )
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
        except Exception as exc:
            # Never leave the job stuck on "running" — surface the failure.
            db.rollback()
            job = db.get(Job, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = f"{type(exc).__name__}: {exc}"[:300]
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
    finally:
        db.close()
