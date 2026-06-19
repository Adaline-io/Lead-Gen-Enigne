"""Pytest fixtures: isolated SQLite DB + async HTTP client against the app.

Environment is configured *before* importing the backend so that
``config.Settings`` validates and ``db.engine`` binds to the throwaway test
database rather than the real ``data/leads.db``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator, Generator

import pytest

# --- Must run before any backend import -------------------------------------
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["SESSION_SECRET"] = "test-session-secret-at-least-32-chars-long-xyz"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["ANTHROPIC_API_KEY"] = "test-key"

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from backend.app import app  # noqa: E402
from backend.auth import hash_password  # noqa: E402
from backend.db import Base, SessionLocal, engine  # noqa: E402
from backend.models import User  # noqa: E402

TEST_PASSWORD = "change_me_first_login"


@pytest.fixture(autouse=True)
def fresh_db() -> Generator[None, None, None]:
    """Recreate all tables and seed a known user before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add_all(
            [
                User(
                    username="aslam",
                    role="sales",
                    display_name="Aslam",
                    password_hash=hash_password(TEST_PASSWORD),
                ),
                User(
                    username="jareer",
                    role="admin",
                    display_name="Jareer",
                    password_hash=hash_password(TEST_PASSWORD),
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac
