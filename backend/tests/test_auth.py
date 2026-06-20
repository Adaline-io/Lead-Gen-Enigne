"""Auth flow tests (CLAUDE.md Phase 1 acceptance)."""

from __future__ import annotations

import httpx
import pytest

from backend.auth import hash_password, verify_password

TEST_PASSWORD = "change_me_first_login"


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert hashed.startswith("$2")  # bcrypt
    assert verify_password("hunter2", hashed) is True
    assert verify_password("wrong", hashed) is False


async def test_login_success_sets_cookie(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "aslam", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["username"] == "aslam"
    assert body["user"]["role"] == "sales"
    assert body["user"]["display_name"] == "Aslam"
    assert "session" in resp.cookies or "set-cookie" in {
        k.lower() for k in resp.headers
    }


async def test_login_unknown_username(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "username not found"


async def test_login_wrong_password(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "aslam", "password": "nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "password incorrect"


async def test_login_missing_fields_returns_422(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/auth/login", json={"username": "aslam"})
    assert resp.status_code == 422
    assert "error" in resp.json()


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "not authenticated"


async def test_me_after_login(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login",
        json={"username": "aslam", "password": TEST_PASSWORD},
    )
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "aslam"


async def test_login_updates_last_login(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "aslam", "password": TEST_PASSWORD},
    )
    assert resp.json()["user"]["last_login"] is not None


async def test_logout_clears_session(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login",
        json={"username": "aslam", "password": TEST_PASSWORD},
    )
    out = await client.post("/api/auth/logout")
    assert out.status_code == 200
    assert out.json()["ok"] is True

    me = await client.get("/api/auth/me")
    assert me.status_code == 401


async def test_change_password(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login", json={"username": "aslam", "password": TEST_PASSWORD}
    )
    # wrong current password rejected
    bad = await client.post(
        "/api/auth/change-password",
        json={"current_password": "nope", "new_password": "brand_new_pw"},
    )
    assert bad.status_code == 400

    # too-short new password rejected
    short = await client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert short.status_code == 400

    # success, then the new password works for login
    ok = await client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "brand_new_pw1"},
    )
    assert ok.status_code == 200
    await client.post("/api/auth/logout")
    relogin = await client.post(
        "/api/auth/login", json={"username": "aslam", "password": "brand_new_pw1"}
    )
    assert relogin.status_code == 200


@pytest.mark.parametrize("username,role", [("aslam", "sales"), ("jareer", "admin")])
async def test_role_reported_correctly(
    client: httpx.AsyncClient, username: str, role: str
) -> None:
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": TEST_PASSWORD},
    )
    assert resp.json()["user"]["role"] == role
