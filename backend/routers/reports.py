"""Reports endpoints: KPI summary + chart data (CLAUDE.md §5)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from backend.auth import current_user, require_admin
from backend.db import get_db
from backend.models import Lead, User
from backend.schemas import (
    ChartDatum,
    PIPELINE_STATUSES,
    RepPerformance,
    RepPerformanceResponse,
    ReportCharts,
    ReportSummary,
    TargetUpdate,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

# Funnel order — how a qualified lead progresses.
_FUNNEL = ("new", "contacted", "replied", "meeting", "won")
_WON = "won"
_LOST = ("lost_poor_fit", "lost_no_response", "lost_declined")


def _date_filter(stmt, frm: str | None, to: str | None):
    if frm:
        stmt = stmt.where(Lead.scraped_at >= datetime.fromisoformat(frm))
    if to:
        stmt = stmt.where(Lead.scraped_at <= datetime.fromisoformat(to))
    return stmt


@router.get("/summary", response_model=ReportSummary)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    frm: str | None = Query(None, alias="from"),
    to: str | None = None,
) -> ReportSummary:
    return _summary(db, frm, to)


def _summary(db: Session, frm: str | None = None, to: str | None = None) -> ReportSummary:
    base = _date_filter(select(Lead).where(Lead.archived.is_(False)), frm, to)
    leads = db.scalars(base).all()

    total = len(leads)
    qualified = sum(1 for lead in leads if lead.qualified)
    scored = [lead.score for lead in leads if lead.score is not None]
    avg_score = round(sum(scored) / len(scored), 2) if scored else 0.0

    counts = {s: 0 for s in (*PIPELINE_STATUSES, *_LOST, "pending")}
    for lead in leads:
        counts[lead.status] = counts.get(lead.status, 0) + 1

    won = counts.get("won", 0)
    closed = won + sum(counts.get(s, 0) for s in _LOST)
    win_rate = round(won / closed * 100, 1) if closed else 0.0
    qual_rate = round(qualified / total * 100, 1) if total else 0.0

    from backend.services.intake import FOLLOWUP_STATUSES, followup_cutoff

    cutoff = followup_cutoff()
    follow_up = sum(
        1
        for lead in leads
        if lead.status in FOLLOWUP_STATUSES
        and (lead.last_contact or lead.scraped_at) is not None
        and (lead.last_contact or lead.scraped_at) < cutoff
    )

    return ReportSummary(
        total=total,
        qualified=qualified,
        qual_rate=qual_rate,
        win_rate=win_rate,
        avg_score=avg_score,
        new=counts.get("new", 0),
        won=won,
        contacted=counts.get("contacted", 0),
        replied=counts.get("replied", 0),
        follow_up=follow_up,
    )


@router.get("/charts", response_model=ReportCharts)
def charts(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ReportCharts:
    leads = db.scalars(select(Lead).where(Lead.archived.is_(False))).all()

    # by_status
    status_counts: dict[str, int] = {}
    vertical_counts: dict[str, int] = {}
    for lead in leads:
        status_counts[lead.status] = status_counts.get(lead.status, 0) + 1
        vertical_counts[lead.vertical_tag] = vertical_counts.get(lead.vertical_tag, 0) + 1

    by_status = [ChartDatum(label=k, value=v) for k, v in sorted(status_counts.items())]
    by_vertical = [
        ChartDatum(label=k, value=v)
        for k, v in sorted(vertical_counts.items(), key=lambda kv: -kv[1])
    ]

    # funnel — cumulative-ish: count of leads currently at or past each stage.
    funnel = []
    for i, stage in enumerate(_FUNNEL):
        reached = sum(
            status_counts.get(s, 0) for s in _FUNNEL[i:]
        )
        funnel.append(ChartDatum(label=stage, value=reached))

    # owner_clicks — leads assigned per owner (display name).
    rows = db.execute(
        select(User.display_name, func.count(Lead.id))
        .join(Lead, Lead.assigned_to == User.id)
        .where(Lead.archived.is_(False))
        .group_by(User.display_name)
    ).all()
    owner_clicks = [ChartDatum(label=name, value=count) for name, count in rows]

    return ReportCharts(
        by_status=by_status,
        by_vertical=by_vertical,
        funnel=funnel,
        owner_clicks=owner_clicks,
    )


_IN_PROGRESS = ("contacted", "replied", "meeting")


@router.get("/reps", response_model=RepPerformanceResponse)
def rep_performance(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RepPerformanceResponse:
    """Per-rep scoreboard: leads, in-progress, confirmed (won), target, achieved."""
    reps = db.scalars(
        select(User).where(User.role.in_(("sales", "admin"))).order_by(User.display_name)
    ).all()
    leads = db.scalars(select(Lead).where(Lead.archived.is_(False))).all()

    rows: list[RepPerformance] = []
    for rep in reps:
        mine = [lead for lead in leads if lead.assigned_to == rep.id]
        confirmed = sum(1 for lead in mine if lead.status == "won")
        in_prog = sum(1 for lead in mine if lead.status in _IN_PROGRESS)
        target = rep.target or 0
        rows.append(RepPerformance(
            id=rep.id,
            name=rep.display_name,
            role=rep.role,
            leads=len(mine),
            in_progress=in_prog,
            confirmed=confirmed,
            target=target,
            achieved_pct=round(confirmed / target * 100, 1) if target else 0.0,
        ))
    # Best performers first.
    rows.sort(key=lambda r: (r.confirmed, r.leads), reverse=True)
    return RepPerformanceResponse(reps=rows)


@router.patch("/reps/{rep_id}", response_model=RepPerformance)
def set_target(
    rep_id: int,
    body: TargetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> RepPerformance:
    """Admins set a rep's target (number of deals to close)."""
    rep = db.get(User, rep_id)
    if rep is None:
        raise HTTPException(404, "user not found")
    rep.target = max(0, body.target)
    db.commit()

    mine = db.scalars(
        select(Lead).where(Lead.assigned_to == rep_id, Lead.archived.is_(False))
    ).all()
    confirmed = sum(1 for lead in mine if lead.status == "won")
    in_prog = sum(1 for lead in mine if lead.status in _IN_PROGRESS)
    return RepPerformance(
        id=rep.id, name=rep.display_name, role=rep.role, leads=len(mine),
        in_progress=in_prog, confirmed=confirmed, target=rep.target,
        achieved_pct=round(confirmed / rep.target * 100, 1) if rep.target else 0.0,
    )
