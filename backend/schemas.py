"""Pydantic request/response schemas."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


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
    enrichment: str | None = None

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
    # Editable business details — filling these in re-scores the lead so a
    # sparse listing can be improved by hand.
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    city: str | None = None
    country: str | None = None
    category: str | None = None
    address: str | None = None
    rating: float | None = None
    review_count: int | None = None


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
    # All optional. Type the industry/niche as `category`; the server infers the
    # scoring rubric (`vertical_tag`) from it unless you pass one explicitly.
    vertical_tag: str | None = None
    query: str | None = None
    category: str | None = None
    keywords: str | None = None
    source: str = "google_maps"          # google_maps | linkedin
    queries: list[str] | None = None     # explicit expanded terms (from the UI)
    expand: bool = False                 # auto-expand the category if no queries
    city: str | None = None
    radius_km: float | None = None
    lat: float | None = None
    lng: float | None = None
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
    source: str = "google_maps"
    queries: list[str] | None = None
    category: str | None = None
    keywords: str | None = None
    radius_m: int | None = None

    @field_validator("queries", mode="before")
    @classmethod
    def _parse_queries(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return None
        return v
    lat: float | None = None
    lng: float | None = None
    lang: str | None = None
    max_results: int | None = None
    extract_emails: bool = False
    started_by: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str
    leads_found: int = 0
    leads_scored: int = 0
    leads_duplicate: int = 0
    error_message: str | None = None

    @field_validator("leads_found", "leads_scored", "leads_duplicate", mode="before")
    @classmethod
    def _int_or_zero(cls, v):
        # Older rows (column added by auto-heal) can be NULL — treat as 0.
        return 0 if v is None else v


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
    follow_up: int = 0


class ChartDatum(BaseModel):
    label: str
    value: int


class ReportCharts(BaseModel):
    by_status: list[ChartDatum]
    by_vertical: list[ChartDatum]
    funnel: list[ChartDatum]
    owner_clicks: list[ChartDatum]


class RepPerformance(BaseModel):
    id: int
    name: str
    role: str
    leads: int          # assigned, not archived
    in_progress: int    # contacted / replied / meeting
    confirmed: int      # won
    target: int
    achieved_pct: float


class RepPerformanceResponse(BaseModel):
    reps: list[RepPerformance]


class TargetUpdate(BaseModel):
    target: int
