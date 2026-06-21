"""Scrape-job endpoints: start, list, detail (CLAUDE.md §5)."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings

from backend.auth import current_user, require_admin
from backend.db import get_db
from backend.models import Job, User
from backend.schemas import (
    JobCreate,
    JobListResponse,
    JobOut,
    JobResponse,
)
import json

from backend.services.expand import expand_queries
from backend.services.geocode import geocode
from backend.services.intake import infer_vertical
from backend.services.scraper import run_scrape_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/geocode")
def geocode_lookup(
    q: str,
    user: User = Depends(current_user),
) -> dict:
    """Resolve a typed location to precise places (for the Find Leads picker)."""
    return {"results": geocode(q)}


@router.get("/expand")
def expand_lookup(
    q: str,
    keywords: str | None = None,
    user: User = Depends(require_admin),
) -> dict:
    """Suggest related search terms for an industry (the Find Leads chips)."""
    return {"terms": expand_queries(q, keywords)}


def _daily_used(db: Session, source: str) -> int:
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(db.scalar(
        select(func.coalesce(func.sum(Job.leads_found), 0)).where(
            Job.source == source, Job.started_at >= start
        )
    ) or 0)


@router.get("/sources")
def sources(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict:
    """Per-source availability (live/demo/off) and today's usage vs cap."""
    from backend.services.linkedin import linkedin_live
    from backend.services.scraper import gosom_live

    def info(name: str, live: bool) -> dict:
        cap = settings.LINKEDIN_DAILY_CAP if name == "linkedin" else settings.GMAPS_DAILY_CAP
        used = _daily_used(db, name)
        return {
            "live": live,
            "mode": "live" if live else ("demo" if settings.SCRAPER_DEMO else "off"),
            "cap": cap,
            "used": used,
            "remaining": max(0, cap - used) if cap else None,
        }

    return {
        "google_maps": info("google_maps", gosom_live()),
        "linkedin": info("linkedin", linkedin_live()),
    }


@router.get("/test-linkedin")
def test_linkedin(user: User = Depends(require_admin)) -> dict:
    """Check LinkedIn credentials before running a full scrape."""
    from backend.services.linkedin import test_connection

    return test_connection()


def _daily_cap_check(db: Session, source: str, requested_max: int | None) -> int | None:
    """Enforce the per-source daily lead cap. Returns the effective max_results."""
    cap = settings.LINKEDIN_DAILY_CAP if source == "linkedin" else settings.GMAPS_DAILY_CAP
    if not cap or cap <= 0:
        return requested_max
    remaining = cap - _daily_used(db, source)
    if remaining <= 0:
        raise HTTPException(
            429,
            f"Daily {source} cap reached ({cap} leads). Try again tomorrow "
            "or raise the cap in .env.",
        )
    return min(requested_max, remaining) if requested_max else remaining


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> JobResponse:
    if body.depth not in (1, 2, 3):
        raise HTTPException(400, "depth must be 1, 2, or 3")

    # Compose the search string from category + keywords if no explicit query.
    base = body.query or " ".join(
        p for p in (body.category, body.keywords) if p
    ).strip()

    # Determine the full set of search terms (the market, not just the phrase).
    if body.queries:
        terms = [t.strip() for t in body.queries if t and t.strip()]
    elif base and body.expand:
        terms = expand_queries(base, body.keywords)
    elif base:
        terms = [base]
    else:
        terms = []
    if not terms:
        raise HTTPException(400, "type an industry or what you're looking for")

    # A clean human label; the full list lives in job.queries.
    label = base or terms[0]
    if len(terms) > 1:
        label = f"{label} (+{len(terms) - 1} related)"

    # Infer the scoring rubric from the typed industry unless one was given.
    vertical_tag = body.vertical_tag or infer_vertical(body.category or terms[0])
    radius_m = int(body.radius_km * 1000) if body.radius_km else None
    source = body.source if body.source in ("google_maps", "linkedin") else "google_maps"

    # Daily safety cap per source (raises 429 if exhausted).
    effective_max = _daily_cap_check(db, source, body.max_results)

    job = Job(
        query=label,
        vertical_tag=vertical_tag,
        depth=body.depth,
        city=body.city,
        source=source,
        queries=json.dumps(terms),
        category=body.category,
        keywords=body.keywords,
        radius_m=radius_m,
        lat=body.lat,
        lng=body.lng,
        lang=body.lang,
        max_results=effective_max,
        extract_emails=body.extract_emails,
        started_by=user.id,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Run the scrape after the response is sent (good enough at this scale).
    background.add_task(run_scrape_job, job.id)

    return JobResponse(job=JobOut.model_validate(job))


@router.get("", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    limit: int = Query(20, le=100),
    status: str | None = None,
) -> JobListResponse:
    stmt = select(Job).order_by(Job.started_at.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    stmt = stmt.limit(limit)
    jobs = db.scalars(stmt).all()
    return JobListResponse(jobs=[JobOut.model_validate(j) for j in jobs])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobResponse(job=JobOut.model_validate(job))
