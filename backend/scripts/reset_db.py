"""Destroy and recreate every table. DEV ONLY — wipes all data.

Run with::

    uv run python -m backend.scripts.reset_db
"""

from __future__ import annotations

from backend.db import Base, create_all, engine
from backend.models import User  # noqa: F401  (ensure models register)


def reset() -> None:
    Base.metadata.drop_all(bind=engine)
    create_all()
    print("Database reset: all tables dropped and recreated.")


if __name__ == "__main__":
    reset()
