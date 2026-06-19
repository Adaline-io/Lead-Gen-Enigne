"""Authentication routes: login, logout, me (CLAUDE.md §5)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user, verify_password
from backend.db import get_db
from backend.models import User
from backend.schemas import LoginRequest, OkResponse, UserOut, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(
    body: LoginRequest, request: Request, db: Session = Depends(get_db)
) -> UserResponse:
    user = db.scalar(select(User).where(User.username == body.username))
    # Honest error messages (CLAUDE.md standing rule #4) — but note both paths
    # return 401 so we never leak which usernames exist via status code alone.
    if user is None:
        raise HTTPException(401, "username not found")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "password incorrect")

    user.last_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return UserResponse(user=UserOut.model_validate(user))


@router.post("/logout", response_model=OkResponse)
def logout(request: Request) -> OkResponse:
    request.session.clear()
    return OkResponse(ok=True)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse(user=UserOut.model_validate(user))
