"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Status taxonomy (CLAUDE.md standing rule #10 — fixed, do not extend lightly)
# ---------------------------------------------------------------------------
STATUSES = (
    "pending",
    "new",
    "contacted",
    "replied",
    "meeting",
    "won",
    "lost_poor_fit",
    "lost_no_response",
    "lost_declined",
    "discarded",
)
Status = Literal[
    "pending",
    "new",
    "contacted",
    "replied",
    "meeting",
    "won",
    "lost_poor_fit",
    "lost_no_response",
    "lost_declined",
    "discarded",
]

# Statuses that count as "in the active pipeline".
PIPELINE_STATUSES = ("new", "contacted", "replied", "meeting", "won")


# --- Auth -------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    display_name: str
    last_login: datetime | None = None


class UserResponse(BaseModel):
    user: UserOut


class OkResponse(BaseModel):
    ok: bool = True


# --- Leads ------------------------------------------------------------------
class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scraped_at: datetime | None = None

    name: str
    category: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    rating: float | None = None
    review_count: int | None = None
    query_used: str | None = None
    vertical_tag: str

    score: float | None = None
    qualified: bool | None = None
    ai_reason: str | None = None
    scored_at: datetime | None = None

    status: str
    assigned_to: int | None = None
    last_contact: datetime | None = None
    next_action: str | None = None
    notes: str | None = None
    outcome: str | None = None

    score_flagged: bool = False
    flag_reason: str | None = None
    archived: bool = False
    lead_tz: str = "Asia/Kolkata"
    whatsapp_url: str | None = None


class LeadCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    country: str | None = None
    category: str | None = None
    address: str | None = None
    website: str | None = None
    rating: float | None = None
    review_count: int | None = None
    vertical_tag: str = "default"
    query_used: str | None = None
    status: Status = "new"
    notes: str | None = None
    assigned_to: int | None = None


class LeadUpdate(BaseModel):
    status: Status | None = None
    assigned_to: int | None = None
    next_action: str | None = None
    notes: str | None = None
    outcome: str | None = None
    last_contact: datetime | None = None
    archived: bool | None = None


class BulkAction(BaseModel):
    ids: list[int]
    action: Literal["status", "assign", "archive"]
    value: Any = None


class FlagRequest(BaseModel):
    reason: str


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    user_id: int
    action: str
    detail: str
    created_at: datetime


class LeadListResponse(BaseModel):
    leads: list[LeadOut]
    total: int


class LeadDetailResponse(BaseModel):
    lead: LeadOut
    activity: list[ActivityOut]


class LeadResponse(BaseModel):
    lead: LeadOut


class BulkResponse(BaseModel):
    updated: int


class ApproveAllRequest(BaseModel):
    job_id: int | None = None


class ApprovedResponse(BaseModel):
    approved: int


# --- Jobs -------------------------------------------------------------------
class JobCreate(BaseModel):
    vertical_tag: str = "default"
    # Either pass a ready-made `query`, or `category` (+ optional `keywords`)
    # and the server composes the search string.
    query: str | None = None
    category: str | None = None
    keywords: str | None = None
    city: str | None = None
    radius_km: float | None = None
    depth: int = 1
    lang: str | None = None
    max_results: int | None = None
    extract_emails: bool = False


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    query: str
    vertical_tag: str
    depth: int
    city: str | None = None
    category: str | None = None
    keywords: str | None = None
    radius_m: int | None = None
    lang: str | None = None
    max_results: int | None = None
    extract_emails: bool = False
    started_by: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    leads_found: int
    leads_scored: int
    error_message: str | None = None


class JobResponse(BaseModel):
    job: JobOut


class JobListResponse(BaseModel):
    jobs: list[JobOut]


# --- Reports ----------------------------------------------------------------
class ReportSummary(BaseModel):
    total: int
    qualified: int
    qual_rate: float
    win_rate: float
    avg_score: float
    new: int
    won: int
    contacted: int
    replied: int


class ChartDatum(BaseModel):
    label: str
    value: int


class ReportCharts(BaseModel):
    by_status: list[ChartDatum]
    by_vertical: list[ChartDatum]
    funnel: list[ChartDatum]
    owner_clicks: list[ChartDatum]
