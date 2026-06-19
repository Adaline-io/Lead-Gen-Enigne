"""Scrape-job endpoints: start, list, detail (CLAUDE.md §5)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import Job, User
from backend.schemas import (
    JobCreate,
    JobListResponse,
    JobOut,
    JobResponse,
)
from backend.services.scraper import run_scrape_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    if body.depth not in (1, 2, 3):
        raise HTTPException(400, "depth must be 1, 2, or 3")

    job = Job(
        query=body.query,
        vertical_tag=body.vertical_tag,
        depth=body.depth,
        city=body.city,
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
