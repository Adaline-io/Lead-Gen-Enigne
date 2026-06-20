"""Query expansion + LinkedIn source (demo) unit tests."""

from __future__ import annotations

import httpx

from backend.services import linkedin
from backend.services.expand import _core, expand_queries

TEST_PASSWORD = "change_me_first_login"


def test_expand_returns_distinct_related_industries() -> None:
    terms = expand_queries("abaya boutiques")
    assert terms[0] == "abaya boutiques"      # base first
    assert len(terms) > 1                       # related industries added
    assert any("modest" in t or "kaftan" in t or "hijab" in t for t in terms)
    # NO reworded synonyms of the base — every core is distinct
    cores = [_core(t) for t in terms]
    assert len(cores) == len(set(cores))
    assert all(c != _core("abaya boutiques") for c in cores[1:])


def test_no_keyword_synonyms() -> None:
    terms = expand_queries("auto parts")
    lowered = [t.lower() for t in terms[1:]]
    assert "auto parts store" not in lowered and "auto parts shop" not in lowered
    assert any("tyre" in t or "battery" in t or "accessories" in t for t in terms)


def test_expand_unknown_without_claude_just_base() -> None:
    # no curated map + no Claude key -> just the base (no fabricated synonyms)
    assert expand_queries("dental clinics") == ["dental clinics"]


def test_expand_empty() -> None:
    assert expand_queries("") == []


def test_linkedin_demo_records(monkeypatch) -> None:
    # disabled + demo mode -> sample records (no creds needed)
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_ENABLED", False)
    monkeypatch.setattr(linkedin.settings, "SCRAPER_DEMO", True)
    recs = linkedin.run_linkedin("marketing agencies", "Dubai")
    assert len(recs) >= 5
    assert recs[0]["contact_name"]              # carries a person name


def test_linkedin_disabled_no_demo_raises(monkeypatch) -> None:
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_ENABLED", False)
    monkeypatch.setattr(linkedin.settings, "SCRAPER_DEMO", False)
    import pytest
    with pytest.raises(RuntimeError):
        linkedin.run_linkedin("x", None)


def test_linkedin_live_flag(monkeypatch) -> None:
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_ENABLED", True)
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_USER", "u@example.com")
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_PASS", "pw")
    assert linkedin.linkedin_live() is True
    monkeypatch.setattr(linkedin.settings, "LINKEDIN_USER", "")
    assert linkedin.linkedin_live() is False


async def test_test_linkedin_endpoint(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    r = await client.get("/api/jobs/test-linkedin")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "message" in body
    assert body["ok"] is False  # disabled by default in tests


async def test_daily_cap_blocks(client: httpx.AsyncClient, monkeypatch) -> None:
    import backend.routers.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "run_scrape_job", lambda jid: None)
    monkeypatch.setattr(jobs_mod.settings, "LINKEDIN_DAILY_CAP", 5)
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    # Seed a job that already used the cap today.
    from datetime import datetime
    from backend.db import SessionLocal
    from backend.models import Job
    db = SessionLocal()
    try:
        db.add(Job(query="x", vertical_tag="default", depth=1, source="linkedin",
                   started_by=1, status="done", leads_found=5,
                   started_at=datetime.utcnow()))
        db.commit()
    finally:
        db.close()
    resp = await client.post(
        "/api/jobs", json={"category": "agencies", "source": "linkedin", "depth": 1}
    )
    assert resp.status_code == 429


async def test_sources_endpoint(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    r = await client.get("/api/jobs/sources")
    assert r.status_code == 200
    body = r.json()
    assert "google_maps" in body and "linkedin" in body
    assert body["linkedin"]["mode"] in ("live", "demo", "off")


async def test_expand_endpoint_admin(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    r = await client.get("/api/jobs/expand?q=auto parts")
    assert r.status_code == 200
    assert len(r.json()["terms"]) > 1


async def test_expand_endpoint_sales_forbidden(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/auth/login", json={"username": "aslam", "password": TEST_PASSWORD}
    )
    assert (await client.get("/api/jobs/expand?q=auto parts")).status_code == 403


async def test_create_job_with_expand(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    r = await client.post(
        "/api/jobs", json={"category": "abaya boutiques", "expand": True, "depth": 1}
    )
    job = r.json()["job"]
    assert job["queries"] and len(job["queries"]) > 1
    assert "related" in job["query"]


async def test_create_job_linkedin_source(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await client.post(
        "/api/auth/login", json={"username": "jareer", "password": TEST_PASSWORD}
    )
    r = await client.post(
        "/api/jobs",
        json={"category": "marketing agencies", "source": "linkedin", "depth": 1},
    )
    assert r.json()["job"]["source"] == "linkedin"
