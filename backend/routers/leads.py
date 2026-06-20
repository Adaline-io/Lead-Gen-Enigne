"""Lead endpoints: list/filter, detail, create, update, bulk, flag, approve."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import Activity, Lead, User
from backend.schemas import (
    ActivityOut,
    ApproveAllRequest,
    ApprovedResponse,
    BulkAction,
    BulkResponse,
    FlagRequest,
    LeadCreate,
    LeadDetailResponse,
    LeadListResponse,
    LeadOut,
    LeadResponse,
    LeadUpdate,
    OkResponse,
    PIPELINE_STATUSES,
    STATUSES,
)
from backend.services.quality import compute_quality
from backend.services.whatsapp import whatsapp_url

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _log(
    db: Session, lead_id: int, user_id: int, action: str, detail: dict
) -> None:
    db.add(
        Activity(
            lead_id=lead_id,
            user_id=user_id,
            action=action,
            detail=json.dumps(detail, default=str),
        )
    )


def _regen_whatsapp(lead: Lead) -> None:
    lead.whatsapp_url = whatsapp_url(
        lead.phone, lead.country, lead.name, lead.city, lead.vertical_tag
    )


_SORTS = {
    "score": Lead.score.desc(),
    "score_asc": Lead.score.asc(),
    "name": Lead.name.asc(),
    "recent": Lead.scraped_at.desc(),
    "oldest": Lead.scraped_at.asc(),
    "rating": Lead.rating.desc(),
}


@router.get("", response_model=LeadListResponse)
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    status: str | None = None,
    owner: str | None = None,
    vertical: str | None = None,
    q: str | None = None,
    sort: str = "score",
    archived: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0,
) -> LeadListResponse:
    stmt = select(Lead).where(Lead.archived == archived)

    if status:
        # Allow comma-separated list, plus the "pipeline" shorthand.
        if status == "pipeline":
            stmt = stmt.where(Lead.status.in_(PIPELINE_STATUSES))
        else:
            wanted = [s.strip() for s in status.split(",") if s.strip()]
            stmt = stmt.where(Lead.status.in_(wanted))
    if vertical:
        stmt = stmt.where(Lead.vertical_tag == vertical)
    if owner:
        if owner == "unassigned":
            stmt = stmt.where(Lead.assigned_to.is_(None))
        elif owner.isdigit():
            stmt = stmt.where(Lead.assigned_to == int(owner))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Lead.name.ilike(like),
                Lead.city.ilike(like),
                Lead.category.ilike(like),
                Lead.address.ilike(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(_SORTS.get(sort, Lead.score.desc()))
    stmt = stmt.limit(limit).offset(offset)
    leads = db.scalars(stmt).all()

    return LeadListResponse(
        leads=[LeadOut.model_validate(lead) for lead in leads], total=total
    )


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> LeadDetailResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    acts = db.scalars(
        select(Activity)
        .where(Activity.lead_id == lead_id)
        .order_by(Activity.created_at.desc())
    ).all()
    return LeadDetailResponse(
        lead=LeadOut.model_validate(lead),
        activity=[ActivityOut.model_validate(a) for a in acts],
    )


@router.post("", response_model=LeadResponse, status_code=201)
def create_lead(
    body: LeadCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> LeadResponse:
    # Dedup on (phone, name) — matches the unique index.
    if body.phone:
        existing = db.scalar(
            select(Lead).where(Lead.phone == body.phone, Lead.name == body.name)
        )
        if existing is not None:
            raise HTTPException(409, "a lead with this phone and name already exists")

    lead = Lead(
        name=body.name,
        phone=body.phone,
        email=body.email,
        city=body.city,
        country=body.country,
        category=body.category,
        address=body.address,
        website=body.website,
        rating=body.rating,
        review_count=body.review_count,
        vertical_tag=body.vertical_tag,
        query_used=body.query_used or "manual entry",
        status=body.status,
        notes=body.notes,
        assigned_to=body.assigned_to,
        scraped_at=datetime.now(timezone.utc),
    )
    # Data-driven quality score from the lead's own fields (CLAUDE.md §8).
    score, qualified, reason = compute_quality(lead)
    lead.score = score
    lead.qualified = qualified
    lead.ai_reason = reason
    lead.scored_at = datetime.now(timezone.utc)

    _regen_whatsapp(lead)
    db.add(lead)
    db.flush()
    _log(db, lead.id, user.id, "note", {"created": "manual entry"})
    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: int,
    body: LeadUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> LeadResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")

    data = body.model_dump(exclude_unset=True)

    if "status" in data and data["status"] != lead.status:
        old = lead.status
        lead.status = data["status"]
        _log(db, lead.id, user.id, "status_change", {"from": old, "to": data["status"]})

    if "assigned_to" in data and data["assigned_to"] != lead.assigned_to:
        lead.assigned_to = data["assigned_to"]
        _log(db, lead.id, user.id, "assign", {"to": data["assigned_to"]})

    if "notes" in data:
        lead.notes = data["notes"]
        _log(db, lead.id, user.id, "note", {"notes": data["notes"]})

    for field in ("next_action", "outcome", "last_contact", "archived"):
        if field in data:
            setattr(lead, field, data[field])

    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.post("/bulk", response_model=BulkResponse)
def bulk(
    body: BulkAction,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> BulkResponse:
    if not body.ids:
        return BulkResponse(updated=0)

    leads = db.scalars(select(Lead).where(Lead.id.in_(body.ids))).all()
    count = 0
    for lead in leads:
        match body.action:
            case "status":
                if body.value not in STATUSES:
                    raise HTTPException(400, f"invalid status: {body.value!r}")
                old = lead.status
                lead.status = body.value
                _log(db, lead.id, user.id, "status_change", {"from": old, "to": body.value})
            case "assign":
                lead.assigned_to = body.value
                _log(db, lead.id, user.id, "assign", {"to": body.value})
            case "archive":
                lead.archived = bool(body.value)
        count += 1

    db.commit()
    return BulkResponse(updated=count)


@router.post("/approve_all", response_model=ApprovedResponse)
def approve_all(
    body: ApproveAllRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ApprovedResponse:
    stmt = select(Lead).where(Lead.status == "pending")
    if body.job_id is not None:
        # leads carry no job FK; match by the job's query string.
        from backend.models import Job

        job = db.get(Job, body.job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        stmt = stmt.where(Lead.query_used == job.query)

    leads = db.scalars(stmt).all()
    for lead in leads:
        lead.status = "new"
        _log(db, lead.id, user.id, "status_change", {"from": "pending", "to": "new"})
    db.commit()
    return ApprovedResponse(approved=len(leads))


@router.post("/{lead_id}/flag", response_model=OkResponse)
def flag(
    lead_id: int,
    body: FlagRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OkResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.score_flagged = True
    lead.flag_reason = body.reason
    _log(db, lead.id, user.id, "flag", {"reason": body.reason})
    db.commit()
    return OkResponse(ok=True)


@router.post("/{lead_id}/approve", response_model=LeadResponse)
def approve(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> LeadResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    if lead.status != "pending":
        raise HTTPException(400, f"lead is not pending (status: {lead.status})")
    lead.status = "new"
    _log(db, lead.id, user.id, "status_change", {"from": "pending", "to": "new"})
    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.post("/{lead_id}/discard", response_model=OkResponse)
def discard(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OkResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.status = "discarded"
    _log(db, lead.id, user.id, "status_change", {"to": "discarded"})
    db.commit()
    return OkResponse(ok=True)
