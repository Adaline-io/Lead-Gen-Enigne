"""Leads CRUD / filter / bulk tests (CLAUDE.md Phase 2 acceptance)."""

from __future__ import annotations

import httpx
import pytest

TEST_PASSWORD = "change_me_first_login"


async def _login(client: httpx.AsyncClient, username: str = "aslam") -> None:
    await client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )


async def _make_lead(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {
        "name": "Hessa Boutique",
        "phone": "+971500000001",
        "city": "Dubai",
        "country": "UAE",
        "vertical_tag": "abaya",
        "status": "new",
    }
    payload.update(overrides)
    resp = await client.post("/api/leads", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["lead"]


async def test_leads_require_auth(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/leads")
    assert resp.status_code == 401


async def test_create_and_list(client: httpx.AsyncClient) -> None:
    await _login(client)
    lead = await _make_lead(client)
    assert lead["name"] == "Hessa Boutique"
    assert lead["whatsapp_url"].startswith("https://wa.me/971500000001")

    resp = await client.get("/api/leads")
    body = resp.json()
    assert body["total"] == 1
    assert len(body["leads"]) == 1


async def test_create_dedup_conflict(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _make_lead(client)
    resp = await client.post(
        "/api/leads",
        json={"name": "Hessa Boutique", "phone": "+971500000001", "vertical_tag": "abaya"},
    )
    assert resp.status_code == 409


async def test_filter_by_status(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _make_lead(client, name="A", phone="111", status="new")
    await _make_lead(client, name="B", phone="222", status="contacted")

    resp = await client.get("/api/leads?status=new")
    body = resp.json()
    assert body["total"] == 1
    assert body["leads"][0]["name"] == "A"


async def test_filter_search_q(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _make_lead(client, name="Dubai Marina Abaya", phone="111", city="Dubai")
    await _make_lead(client, name="Riyadh Store", phone="222", city="Riyadh")

    resp = await client.get("/api/leads?q=Marina")
    assert resp.json()["total"] == 1


async def test_patch_status_logs_activity(client: httpx.AsyncClient) -> None:
    await _login(client)
    lead = await _make_lead(client)

    resp = await client.patch(
        f"/api/leads/{lead['id']}",
        json={"status": "contacted", "notes": "reached out via WA"},
    )
    assert resp.status_code == 200
    assert resp.json()["lead"]["status"] == "contacted"

    detail = await client.get(f"/api/leads/{lead['id']}")
    actions = {a["action"] for a in detail.json()["activity"]}
    assert "status_change" in actions
    assert "note" in actions


async def test_bulk_status(client: httpx.AsyncClient) -> None:
    await _login(client)
    a = await _make_lead(client, name="A", phone="111")
    b = await _make_lead(client, name="B", phone="222")

    resp = await client.post(
        "/api/leads/bulk",
        json={"ids": [a["id"], b["id"]], "action": "status", "value": "won"},
    )
    assert resp.json()["updated"] == 2
    listing = await client.get("/api/leads?status=won")
    assert listing.json()["total"] == 2


async def test_bulk_invalid_status_rejected(client: httpx.AsyncClient) -> None:
    await _login(client)
    a = await _make_lead(client)
    resp = await client.post(
        "/api/leads/bulk",
        json={"ids": [a["id"]], "action": "status", "value": "bogus"},
    )
    assert resp.status_code == 400


async def test_approve_and_discard(client: httpx.AsyncClient) -> None:
    await _login(client)
    pend = await _make_lead(client, name="P", phone="111", status="pending")
    disc = await _make_lead(client, name="D", phone="222", status="pending")

    ok = await client.post(f"/api/leads/{pend['id']}/approve")
    assert ok.json()["lead"]["status"] == "new"

    dd = await client.post(f"/api/leads/{disc['id']}/discard")
    assert dd.json()["ok"] is True

    # approving a non-pending lead is a 400
    again = await client.post(f"/api/leads/{pend['id']}/approve")
    assert again.status_code == 400


async def test_flag(client: httpx.AsyncClient) -> None:
    await _login(client)
    lead = await _make_lead(client)
    resp = await client.post(
        f"/api/leads/{lead['id']}/flag", json={"reason": "score too high"}
    )
    assert resp.json()["ok"] is True
    detail = await client.get(f"/api/leads/{lead['id']}")
    assert detail.json()["lead"]["score_flagged"] is True


async def test_get_missing_lead_404(client: httpx.AsyncClient) -> None:
    await _login(client)
    resp = await client.get("/api/leads/9999")
    assert resp.status_code == 404
