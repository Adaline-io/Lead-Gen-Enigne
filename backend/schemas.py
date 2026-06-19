"""Pydantic request/response schemas.

Phase 1 only needs the auth-related shapes. Lead/Job/Report schemas land in
their respective phases.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    display_name: str
    last_login: datetime | None = None


class UserResponse(BaseModel):
    user: UserOut


class OkResponse(BaseModel):
    ok: bool = True
