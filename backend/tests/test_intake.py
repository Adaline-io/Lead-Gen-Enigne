"""Tests for intake logic + CSV import/export + follow-up + auto-assign."""

from __future__ import annotations

import io

import httpx

from backend.db import SessionLocal
from backend.models import Lead
from backend.services.intake import (
    find_duplicate,
    known_client_flag,
    normalize_name,
)

TEST_PASSWORD = "change_me_first_login"


async def _login(client: httpx.AsyncClient, username: str = "aslam") -> None:
    await client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )


# --- pure helpers ----------------------------------------------------------
def test_normalize_name_strips_suffixes() -> None:
    assert normalize_name("Al Noor Trading LLC") == "al noor"
    assert normalize_name("Hessa Boutique") == normalize_name("hessa  boutique!")


def test_known_client_flag() -> None:
    assert known_client_flag("ALIFA Couture") is not None
    assert known_client_flag("Roca Spare Parts") is not None
    assert known_client_flag("Some Other Shop") is None


def test_find_duplicate_by_name_and_city() -> None:
    db = SessionLocal()
    try:
        db.add(Lead(name="Hessa Boutique", city="Dubai", vertical_tag="abaya", phone="111"))
        db.commit()
        dup = find_duplicate(db, name="hessa boutique", phone=None, city="Dubai", website=None)
        assert dup is not None
        none = find_duplicate(db, name="Other", phone=None, city="Dubai", website=None)
        assert none is None
    finally:
        db.close()


# --- endpoints -------------------------------------------------------------
async def test_csv_export(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post("/api/leads", json={
        "name": "Hessa Boutique", "phone": "+971500000001", "city": "Dubai",
        "country": "UAE", "vertical_tag": "abaya", "status": "new",
    })
    resp = await client.get("/api/leads/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert "name,category,city" in body.splitlines()[0]
    assert "Hessa Boutique" in body


async def test_csv_import_scores_and_dedups(client: httpx.AsyncClient) -> None:
    await _login(client)
    csv_text = (
        "title,phone,city,country,website,review_rating,review_count\n"
        "Layali Couture,+971500000010,Dubai,UAE,https://layali.ae,4.8,210\n"
        "Layali Couture,+971500000010,Dubai,UAE,https://layali.ae,4.8,210\n"  # dup
        ",,,,,,\n"  # blank name -> skipped
    )
    files = {"file": ("leads.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    resp = await client.post(
        "/api/leads/import", files=files, data={"default_vertical": "abaya"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 2

    listing = await client.get("/api/leads?q=Layali")
    lead = listing.json()["leads"][0]
    assert lead["score"] is not None and lead["qualified"] is True
    assert lead["status"] == "new"


async def test_approve_auto_assigns_to_approver(client: httpx.AsyncClient) -> None:
    await _login(client, "aslam")
    created = await client.post("/api/leads", json={
        "name": "Pending Co", "phone": "+971500000020", "vertical_tag": "abaya",
        "status": "pending",
    })
    lid = created.json()["lead"]["id"]
    resp = await client.post(f"/api/leads/{lid}/approve")
    lead = resp.json()["lead"]
    assert lead["status"] == "new"
    assert lead["assigned_to"] is not None  # auto-assigned


async def test_known_client_flagged_on_create(client: httpx.AsyncClient) -> None:
    await _login(client)
    resp = await client.post("/api/leads", json={
        "name": "ALIFA Atelier", "phone": "+971500000030", "vertical_tag": "abaya",
        "status": "new",
    })
    lead = resp.json()["lead"]
    assert lead["score_flagged"] is True
    assert "existing client" in (lead["flag_reason"] or "").lower()


async def test_follow_up_filter(client: httpx.AsyncClient) -> None:
    await _login(client)
    # Create a contacted lead, then backdate its last_contact past the cutoff.
    created = await client.post("/api/leads", json={
        "name": "Stale Lead", "phone": "+971500000040", "vertical_tag": "abaya",
        "status": "contacted",
    })
    lid = created.json()["lead"]["id"]

    db = SessionLocal()
    try:
        from datetime import datetime, timedelta
        lead = db.get(Lead, lid)
        lead.last_contact = datetime.utcnow() - timedelta(days=10)
        db.commit()
    finally:
        db.close()

    resp = await client.get("/api/leads?follow_up=true")
    names = [lead_["name"] for lead_ in resp.json()["leads"]]
    assert "Stale Lead" in names
