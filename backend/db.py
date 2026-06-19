"""Database engine, session factory, and the ``get_db`` FastAPI dependency."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _ensure_sqlite_dir(url: str) -> None:
    """For file-based SQLite URLs, make sure the parent directory exists."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        path = url[len(prefix):]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def _engine_kwargs(url: str) -> dict:
    # SQLite needs check_same_thread=False so the connection can be shared
    # across FastAPI's threadpool. Other backends use defaults.
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


_ensure_sqlite_dir(settings.DATABASE_URL)

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    **_engine_kwargs(settings.DATABASE_URL),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_all() -> None:
    """Create every table. Convenient for dev/MVP; Alembic owns prod schema."""
    # Import models so they register on Base.metadata before create_all.
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session, ensuring it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
