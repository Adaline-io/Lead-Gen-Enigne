"""Authentication routes: login, logout, me (CLAUDE.md §5)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user, hash_password, verify_password
from backend.db import get_db
from backend.models import User
from backend.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    OkResponse,
    UserOut,
    UserResponse,
)
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UsersResponse(BaseModel):
    users: list[UserOut]


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


@router.post("/change-password", response_model=OkResponse)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> OkResponse:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(400, "new password must be at least 8 characters")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return OkResponse(ok=True)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse(user=UserOut.model_validate(user))


@router.get("/users", response_model=UsersResponse)
def users(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> UsersResponse:
    """Team roster — used by the UI to resolve owners and populate assign menus."""
    rows = db.scalars(select(User).order_by(User.display_name)).all()
    return UsersResponse(users=[UserOut.model_validate(u) for u in rows])
