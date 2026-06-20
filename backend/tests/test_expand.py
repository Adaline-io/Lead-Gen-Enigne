"""Query expansion + LinkedIn source (demo) unit tests."""

from __future__ import annotations

import httpx

from backend.services import linkedin
from backend.services.expand import expand_queries

TEST_PASSWORD = "change_me_first_login"


def test_expand_includes_base_and_related() -> None:
    terms = expand_queries("abaya boutiques")
    assert terms[0] == "abaya boutiques"      # base first
    assert len(terms) > 1                       # related added
    assert any("modest" in t or "kaftan" in t or "islamic" in t for t in terms)


def test_expand_unknown_industry_generic() -> None:
    terms = expand_queries("dental clinics")
    assert "dental clinics" in terms
    assert len(terms) > 1


def test_expand_empty() -> None:
    assert expand_queries("") == []


def test_linkedin_demo_records() -> None:
    # disabled + demo mode -> sample records (no creds needed)
    linkedin.settings.LINKEDIN_ENABLED = False
    linkedin.settings.SCRAPER_DEMO = True
    recs = linkedin.run_linkedin("marketing agencies", "Dubai")
    assert len(recs) >= 5
    assert recs[0]["contact_name"]              # carries a person name


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
