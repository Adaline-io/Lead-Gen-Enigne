"""Lead endpoints: list/filter, detail, create, update, bulk, flag, approve."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.auth import current_user, require_admin, require_writer
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
from backend.services.intake import (
    FOLLOWUP_STATUSES,
    find_duplicate,
    followup_cutoff,
    known_client_flag,
    pick_round_robin,
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


def _regen_whatsapp(db: Session, lead: Lead) -> None:
    """Rebuild the WhatsApp link, signed by the assigned rep (so the outreach
    message carries the name of whoever actually works the lead)."""
    rep = None
    if lead.assigned_to:
        owner = db.get(User, lead.assigned_to)
        rep = owner.display_name if owner else None
    lead.whatsapp_url = whatsapp_url(
        lead.phone, lead.country, lead.name, lead.city, lead.vertical_tag, rep
    )


_SORTS = {
    "score": Lead.score.desc(),
    "score_asc": Lead.score.asc(),
    "name": Lead.name.asc(),
    "recent": Lead.scraped_at.desc(),
    "oldest": Lead.scraped_at.asc(),
    "rating": Lead.rating.desc(),
}


def _filtered_stmt(
    *,
    status: str | None,
    owner: str | None,
    vertical: str | None,
    q: str | None,
    archived: bool,
    follow_up: bool,
):
    stmt = select(Lead).where(Lead.archived == archived)

    if follow_up:
        # Active, awaiting-reply leads with no fresh contact for FOLLOWUP_DAYS.
        stmt = stmt.where(
            Lead.status.in_(FOLLOWUP_STATUSES),
            func.coalesce(Lead.last_contact, Lead.scraped_at) < followup_cutoff(),
        )
    elif status:
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
    return stmt


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
    follow_up: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0,
) -> LeadListResponse:
    stmt = _filtered_stmt(
        status=status, owner=owner, vertical=vertical, q=q,
        archived=archived, follow_up=follow_up,
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    stmt = stmt.order_by(_SORTS.get(sort, Lead.score.desc()))
    stmt = stmt.limit(limit).offset(offset)
    leads = db.scalars(stmt).all()

    return LeadListResponse(
        leads=[LeadOut.model_validate(lead) for lead in leads], total=total
    )


_EXPORT_COLUMNS = [
    "name", "category", "city", "country", "phone", "email", "website",
    "rating", "review_count", "vertical_tag", "score", "qualified", "status",
    "owner", "ai_reason", "next_action", "notes", "whatsapp_url",
]


@router.get("/export.csv")
def export_csv(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    status: str | None = None,
    owner: str | None = None,
    vertical: str | None = None,
    q: str | None = None,
    archived: bool = False,
    follow_up: bool = False,
) -> StreamingResponse:
    """Download the currently-filtered leads as a CSV (for spreadsheets)."""
    stmt = _filtered_stmt(
        status=status, owner=owner, vertical=vertical, q=q,
        archived=archived, follow_up=follow_up,
    ).order_by(Lead.score.desc())
    leads = db.scalars(stmt).all()
    names = {u.id: u.display_name for u in db.scalars(select(User)).all()}

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for lead in leads:
        writer.writerow([
            lead.name, lead.category, lead.city, lead.country, lead.phone,
            lead.email, lead.website, lead.rating, lead.review_count,
            lead.vertical_tag, lead.score, lead.qualified, lead.status,
            names.get(lead.assigned_to, ""), lead.ai_reason, lead.next_action,
            lead.notes, lead.whatsapp_url,
        ])
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="leads_{stamp}.csv"'},
    )


# Flexible CSV header aliases → our field names (also accepts gosom CSV output).
_IMPORT_ALIASES = {
    "name": ("name", "title", "business", "business_name", "company"),
    "phone": ("phone", "phone_number", "mobile", "tel"),
    "email": ("email", "emails", "e-mail"),
    "city": ("city", "town"),
    "country": ("country",),
    "website": ("website", "web_site", "url", "site"),
    "rating": ("rating", "review_rating", "stars", "score"),
    "review_count": ("review_count", "reviews", "num_reviews", "ratings"),
    "category": ("category", "type", "business_type"),
    "address": ("address", "complete_address", "full_address"),
    "vertical_tag": ("vertical_tag", "vertical", "industry"),
}


def _pick(row: dict, field: str) -> str | None:
    for alias in _IMPORT_ALIASES[field]:
        if alias in row and str(row[alias]).strip():
            return str(row[alias]).strip()
    return None


@router.post("/import")
async def import_csv(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
    file: UploadFile = File(...),
    default_vertical: str = Form("default"),
) -> dict:
    """Import leads from a CSV (your spreadsheet, or a gosom export)."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(400, "the CSV file appears to be empty")
    # normalize headers to lowercase
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]

    imported = skipped = 0
    for raw_row in reader:
        row = {(k or "").strip().lower(): v for k, v in raw_row.items()}
        name = _pick(row, "name")
        if not name:
            skipped += 1
            continue

        phone = _pick(row, "phone")
        city = _pick(row, "city")
        website = _pick(row, "website")
        if find_duplicate(db, name=name, phone=phone, city=city, website=website):
            skipped += 1
            continue

        def _num(v, cast):
            try:
                return cast(v)
            except (TypeError, ValueError):
                return None

        email = _pick(row, "email")
        if email and "," in email:
            email = email.split(",")[0].strip()

        lead = Lead(
            name=name,
            phone=phone,
            email=email,
            city=city,
            country=_pick(row, "country"),
            website=website,
            category=_pick(row, "category"),
            address=_pick(row, "address"),
            rating=_num(_pick(row, "rating"), float),
            review_count=_num(_pick(row, "review_count"), lambda x: int(float(x))),
            vertical_tag=_pick(row, "vertical_tag") or default_vertical,
            query_used="csv import",
            status="new",
            scraped_at=datetime.now(timezone.utc),
        )
        lead.score, lead.qualified, lead.ai_reason = compute_quality(lead)
        lead.scored_at = datetime.now(timezone.utc)
        cflag = known_client_flag(lead.name)
        if cflag:
            lead.score_flagged = True
            lead.flag_reason = cflag
        _regen_whatsapp(db, lead)

        db.add(lead)
        try:
            db.flush()
        except Exception:
            db.rollback()
            skipped += 1
            continue
        _log(db, lead.id, user.id, "note", {"created": "csv import"})
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}


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
    user: User = Depends(require_writer),
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

    flag = known_client_flag(lead.name)
    if flag:
        lead.score_flagged = True
        lead.flag_reason = flag

    _regen_whatsapp(db, lead)
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
    user: User = Depends(require_writer),
) -> LeadResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")

    data = body.model_dump(exclude_unset=True)

    # Re-assigning ownership is an admin action (admins channel leads to reps).
    if "assigned_to" in data and data["assigned_to"] != lead.assigned_to and user.role != "admin":
        raise HTTPException(403, "only admins can re-assign leads")

    if "status" in data and data["status"] != lead.status:
        old = lead.status
        lead.status = data["status"]
        _log(db, lead.id, user.id, "status_change", {"from": old, "to": data["status"]})

    if "assigned_to" in data and data["assigned_to"] != lead.assigned_to:
        lead.assigned_to = data["assigned_to"]
        _log(db, lead.id, user.id, "assign", {"to": data["assigned_to"]})
        _regen_whatsapp(db, lead)  # re-sign the message with the new owner

    if "notes" in data:
        lead.notes = data["notes"]
        _log(db, lead.id, user.id, "note", {"notes": data["notes"]})

    for field in ("next_action", "outcome", "last_contact", "archived"):
        if field in data:
            setattr(lead, field, data[field])

    # Editing the business details re-scores the lead and refreshes the
    # WhatsApp link — so filling in a sparse listing by hand lifts the score.
    detail_fields = (
        "name", "phone", "email", "website", "city", "country",
        "category", "address", "rating", "review_count",
    )
    edited = [f for f in detail_fields if f in data]
    if edited:
        for field in edited:
            setattr(lead, field, data[field])
        score, qualified, reason = compute_quality(lead)
        lead.score = score
        lead.qualified = qualified
        lead.ai_reason = reason
        lead.scored_at = datetime.now(timezone.utc)
        _regen_whatsapp(db, lead)
        _log(db, lead.id, user.id, "note", {"edited": ", ".join(edited)})

    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.post("/bulk", response_model=BulkResponse)
def bulk(
    body: BulkAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> BulkResponse:
    if not body.ids:
        return BulkResponse(updated=0)
    if body.action == "assign" and user.role != "admin":
        raise HTTPException(403, "only admins can assign leads")

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
                _regen_whatsapp(db, lead)
            case "archive":
                lead.archived = bool(body.value)
        count += 1

    db.commit()
    return BulkResponse(updated=count)


@router.post("/approve_all", response_model=ApprovedResponse)
def approve_all(
    body: ApproveAllRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
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
        # Round-robin across the team so approved leads get distributed.
        if lead.assigned_to is None:
            lead.assigned_to = pick_round_robin(db)
            if lead.assigned_to is not None:
                _log(db, lead.id, user.id, "assign", {"to": lead.assigned_to, "auto": True})
                _regen_whatsapp(db, lead)
        _log(db, lead.id, user.id, "status_change", {"from": "pending", "to": "new"})
    db.commit()
    return ApprovedResponse(approved=len(leads))


@router.post("/{lead_id}/contacted", response_model=LeadResponse)
def mark_contacted(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
) -> LeadResponse:
    """Record an outreach: stamp last_contact, advance new → contacted, log it."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.last_contact = datetime.now(timezone.utc)
    if lead.status == "new":
        lead.status = "contacted"
        _log(db, lead.id, user.id, "status_change", {"from": "new", "to": "contacted"})
    _log(db, lead.id, user.id, "contact", {"via": "whatsapp"})
    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.post("/{lead_id}/flag", response_model=OkResponse)
def flag(
    lead_id: int,
    body: FlagRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_writer),
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
    user: User = Depends(require_admin),
) -> LeadResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    if lead.status != "pending":
        raise HTTPException(400, f"lead is not pending (status: {lead.status})")
    lead.status = "new"
    # The person approving takes ownership (simple + predictable).
    if lead.assigned_to is None:
        lead.assigned_to = user.id
        _log(db, lead.id, user.id, "assign", {"to": user.id, "auto": True})
        _regen_whatsapp(db, lead)
    _log(db, lead.id, user.id, "status_change", {"from": "pending", "to": "new"})
    db.commit()
    db.refresh(lead)
    return LeadResponse(lead=LeadOut.model_validate(lead))


@router.post("/{lead_id}/discard", response_model=OkResponse)
def discard(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> OkResponse:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404, "lead not found")
    lead.status = "discarded"
    _log(db, lead.id, user.id, "status_change", {"to": "discarded"})
    db.commit()
    return OkResponse(ok=True)
