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
    sync_schema()


def sync_schema() -> None:
    """Add any model columns missing from existing tables (dev/MVP self-heal).

    ``create_all`` only creates *missing tables*, never missing columns. When a
    new column is added to a model (e.g. ``leads.enrichment``), an older local
    SQLite file would be out of sync and every query on that table would fail.
    This adds the missing columns with a plain ``ALTER TABLE ADD COLUMN`` so the
    app keeps working after a pull without anyone running Alembic by hand.
    """
    from sqlalchemy import inspect, text

    from backend import models  # noqa: F401

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            coltype = col.type.compile(dialect=engine.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
            if col.server_default is not None:
                ddl += f" DEFAULT {col.server_default.arg}"
                if not col.nullable:
                    ddl += " NOT NULL"
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception:
                # Best-effort: a partial/odd schema shouldn't block startup.
                pass


def get_db() -> Generator[Session, None, None]:
    """Yield a database session, ensuring it is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
