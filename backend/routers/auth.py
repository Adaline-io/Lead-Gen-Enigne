"""Authentication routes: login, logout, me (CLAUDE.md §5)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.auth import current_user, hash_password, require_admin, verify_password
from backend.db import get_db
from backend.models import Lead, User
from backend.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    OkResponse,
    UserCreate,
    UserOut,
    UserResponse,
    UserUpdate,
)
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

ROLES = {"admin", "sales", "viewer"}
MIN_PASSWORD = 6


def _admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    ) or 0


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


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """Admin adds a teammate (sales / admin / viewer)."""
    uname = (body.username or "").strip().lower()
    if not uname:
        raise HTTPException(400, "username is required")
    if body.role not in ROLES:
        raise HTTPException(400, f"role must be one of: {', '.join(sorted(ROLES))}")
    if len(body.password or "") < MIN_PASSWORD:
        raise HTTPException(400, f"password must be at least {MIN_PASSWORD} characters")
    if db.scalar(select(User).where(User.username == uname)):
        raise HTTPException(409, f"username '{uname}' is already taken")

    u = User(
        username=uname,
        display_name=(body.display_name or "").strip() or uname.title(),
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return UserResponse(user=UserOut.model_validate(u))


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserResponse:
    """Admin changes a teammate's role / name / password."""
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")

    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, f"role must be one of: {', '.join(sorted(ROLES))}")
        # Never strip the last admin (would lock everyone out of admin actions).
        if u.role == "admin" and body.role != "admin" and _admin_count(db) <= 1:
            raise HTTPException(400, "can't change the only admin — promote someone first")
        u.role = body.role
    if body.display_name is not None and body.display_name.strip():
        u.display_name = body.display_name.strip()
    if body.password:
        if len(body.password) < MIN_PASSWORD:
            raise HTTPException(400, f"password must be at least {MIN_PASSWORD} characters")
        u.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(u)
    return UserResponse(user=UserOut.model_validate(u))


@router.delete("/users/{user_id}", response_model=OkResponse)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> OkResponse:
    """Admin removes a teammate. Their leads become unassigned."""
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if u.id == admin.id:
        raise HTTPException(400, "you can't remove your own account")
    if u.role == "admin" and _admin_count(db) <= 1:
        raise HTTPException(400, "can't remove the only admin")

    # Unassign their leads so nothing is orphaned.
    for lead in db.scalars(select(Lead).where(Lead.assigned_to == u.id)).all():
        lead.assigned_to = None
    db.delete(u)
    db.commit()
    return OkResponse(ok=True)
