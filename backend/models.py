"""SQLAlchemy 2.x ORM models (see CLAUDE.md §4).

All four tables are defined here so the initial schema/migration is complete,
even though only ``users`` is exercised by Phase 1 (auth).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="sales")  # admin|sales|viewer
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        # Dedup on insert: a given phone+name pair only exists once.
        Index("uq_leads_phone_name", "phone", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # from scraper
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_used: Mapped[str] = mapped_column(String(512), default="")
    vertical_tag: Mapped[str] = mapped_column(String(64), default="default")

    # from scorer
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # sales workflow
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    last_contact: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # quality control
    score_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lead_tz: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    whatsapp_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    assignee: Mapped[User | None] = relationship("User", lazy="joined")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(512))
    vertical_tag: Mapped[str] = mapped_column(String(64))
    depth: Mapped[int] = mapped_column(Integer, default=1)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # queued|running|scoring|done|failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    leads_found: Mapped[int] = mapped_column(Integer, default=0)
    leads_scored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # status_change|note|assign|contact|flag
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
