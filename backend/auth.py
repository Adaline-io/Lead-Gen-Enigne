"""Password hashing and session-based authentication helpers (CLAUDE.md §6)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import User

pwd = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12)


def hash_password(pw: str) -> str:
    return pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    return pwd.verify(pw, hashed)


def current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Resolve the logged-in user from the session cookie, or 401."""
    uid = request.session.get("user_id")
    if not uid:
        raise HTTPException(401, "not authenticated")
    user = db.get(User, uid)
    if not user:
        request.session.clear()
        raise HTTPException(401, "user no longer exists")
    return user


def require_role(*roles: str):
    """Dependency factory: require the current user to hold one of ``roles``."""

    def _dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "insufficient permissions")
        return user

    return _dep


def require_admin(user: User = Depends(current_user)) -> User:
    """Admins run scrapes, approve leads and assign them to reps."""
    if user.role != "admin":
        raise HTTPException(403, "admins only — ask an admin to run this")
    return user


def require_writer(user: User = Depends(current_user)) -> User:
    """Admins and sales reps can edit; viewers are read-only."""
    if user.role not in ("admin", "sales"):
        raise HTTPException(403, "your account is read-only")
    return user
