"""Reports: summary, rep performance, target setting."""

from __future__ import annotations

import httpx

TEST_PASSWORD = "change_me_first_login"


async def _login(client: httpx.AsyncClient, username: str = "jareer") -> None:
    await client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )


async def test_summary_and_charts(client: httpx.AsyncClient) -> None:
    await _login(client)
    assert (await client.get("/api/reports/summary")).status_code == 200
    assert (await client.get("/api/reports/charts")).status_code == 200


async def test_rep_performance_shape(client: httpx.AsyncClient) -> None:
    await _login(client)
    resp = await client.get("/api/reports/reps")
    assert resp.status_code == 200
    reps = resp.json()["reps"]
    assert len(reps) >= 1
    r = reps[0]
    for key in ("id", "name", "leads", "in_progress", "confirmed", "target", "achieved_pct"):
        assert key in r
    assert r["target"] == 5  # default


async def test_set_target_admin_only(client: httpx.AsyncClient) -> None:
    # admin can set a target; achieved% recomputes
    await _login(client, "jareer")
    reps = (await client.get("/api/reports/reps")).json()["reps"]
    rid = reps[0]["id"]
    resp = await client.patch(f"/api/reports/reps/{rid}", json={"target": 4})
    assert resp.status_code == 200
    assert resp.json()["target"] == 4

    # sales rep cannot
    await client.post("/api/auth/logout")
    await _login(client, "aslam")
    denied = await client.patch(f"/api/reports/reps/{rid}", json={"target": 9})
    assert denied.status_code == 403
