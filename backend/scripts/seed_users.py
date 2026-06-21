"""Seed the initial sales-team accounts.

Idempotent: re-running updates display name/role for existing usernames. The
default password (``admin`` for now) is (re)applied to every seeded account so
the whole team shares one known login — each user changes it after first login.

Run with::

    uv run python -m backend.scripts.seed_users
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

# --- Bootstrap SESSION_SECRET before importing config ------------------------
# config.py refuses to import without a valid SESSION_SECRET. For first-run
# convenience we generate one into .env if it's missing (CLAUDE.md §6/§15).


def _ensure_session_secret() -> None:
    if os.environ.get("SESSION_SECRET") and len(os.environ["SESSION_SECRET"]) >= 32:
        return

    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    for line in lines:
        if line.startswith("SESSION_SECRET="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 32 and "replace_with" not in value:
                os.environ["SESSION_SECRET"] = value
                return

    # Generate a fresh secret and persist it.
    new_secret = secrets.token_urlsafe(48)
    os.environ["SESSION_SECRET"] = new_secret
    kept = [ln for ln in lines if not ln.startswith("SESSION_SECRET=")]
    kept.insert(0, f"SESSION_SECRET={new_secret}")
    env_path.write_text("\n".join(kept) + "\n")
    print(f"Generated a new SESSION_SECRET and wrote it to {env_path.resolve()}")


_ensure_session_secret()

# --- Now safe to import the app stack ---------------------------------------
from backend.auth import hash_password  # noqa: E402
from backend.db import SessionLocal, create_all  # noqa: E402
from backend.models import User  # noqa: E402

DEFAULT_PASSWORD = "admin"

SEED_USERS: list[dict[str, str]] = [
    {"username": "jareer", "role": "admin", "display_name": "Jareer"},
    {"username": "ibrahim", "role": "admin", "display_name": "Ibrahim"},
    {"username": "aslam", "role": "sales", "display_name": "Aslam"},
    {"username": "shijas", "role": "sales", "display_name": "Shijas"},
    {"username": "sales1", "role": "sales", "display_name": "Sales Rep"},
]


def seed() -> None:
    create_all()
    db = SessionLocal()
    created, updated = 0, 0
    try:
        seeded_usernames = {spec["username"] for spec in SEED_USERS}
        for spec in SEED_USERS:
            existing = (
                db.query(User).filter(User.username == spec["username"]).one_or_none()
            )
            if existing is None:
                db.add(
                    User(
                        username=spec["username"],
                        role=spec["role"],
                        display_name=spec["display_name"],
                        password_hash=hash_password(DEFAULT_PASSWORD),
                    )
                )
                created += 1
            else:
                existing.role = spec["role"]
                existing.display_name = spec["display_name"]
                # Reset to the shared default so the whole team has one login.
                existing.password_hash = hash_password(DEFAULT_PASSWORD)
                updated += 1

        # Guarantee EVERY account shares the same password — also reset any
        # extra users that aren't in the seed list above.
        others = db.query(User).filter(User.username.notin_(seeded_usernames)).all()
        for u in others:
            u.password_hash = hash_password(DEFAULT_PASSWORD)
            updated += 1
        db.commit()
    finally:
        db.close()

    print(f"Seed complete: {created} created, {updated} updated.")
    print(f"Default password for ALL accounts: {DEFAULT_PASSWORD!r}")
    print("⚠  Each user MUST change this on first login (no reset flow in MVP).")


if __name__ == "__main__":
    seed()
