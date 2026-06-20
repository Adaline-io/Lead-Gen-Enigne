"""Jobs API + scraper mapping/orchestration tests (no real gosom run)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from backend.db import SessionLocal
from backend.models import Job, Lead
from backend.services import scraper

TEST_PASSWORD = "change_me_first_login"


async def _login(client: httpx.AsyncClient, username: str = "jareer") -> None:
    # Scraping is admin-only; default to the admin account.
    await client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )


async def test_sales_cannot_scrape(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client, "aslam")  # sales rep
    resp = await client.post("/api/jobs", json={"category": "abaya", "depth": 1})
    assert resp.status_code == 403


async def test_create_job_queues_background(client: httpx.AsyncClient, monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        "backend.routers.jobs.run_scrape_job", lambda jid: calls.append(jid)
    )
    await _login(client)

    resp = await client.post(
        "/api/jobs",
        json={
            "vertical_tag": "abaya",
            "category": "abaya boutique",
            "keywords": "premium",
            "city": "Dubai Marina",
            "radius_km": 10,
            "depth": 1,
            "lang": "en",
            "max_results": 100,
            "extract_emails": True,
        },
    )
    assert resp.status_code == 201
    job = resp.json()["job"]
    assert job["status"] == "queued"
    assert job["vertical_tag"] == "abaya"
    # category + keywords composed into the search query
    assert job["query"] == "abaya boutique premium"
    assert job["radius_m"] == 10000
    assert job["extract_emails"] is True
    assert calls == [job["id"]]


async def test_create_job_requires_category_or_query(
    client: httpx.AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client)
    resp = await client.post("/api/jobs", json={"depth": 1})
    assert resp.status_code == 400


async def test_geocode_endpoint(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.routers.jobs.geocode",
        lambda q: [{"label": "Dubai Marina, Dubai, UAE", "short": "Dubai Marina",
                    "lat": 25.08, "lon": 55.14}],
    )
    await _login(client)
    r = await client.get("/api/jobs/geocode?q=dubai marina")
    assert r.status_code == 200
    assert r.json()["results"][0]["short"] == "Dubai Marina"


async def test_create_job_stores_coords(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client)
    r = await client.post("/api/jobs", json={
        "category": "abaya boutiques", "city": "Dubai Marina",
        "lat": 25.08, "lng": 55.14, "radius_km": 5, "depth": 1,
    })
    job = r.json()["job"]
    assert job["lat"] == 25.08 and job["lng"] == 55.14
    assert job["radius_m"] == 5000


async def test_create_job_infers_vertical_from_industry(
    client: httpx.AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client)
    # No vertical_tag passed — inferred from the typed industry.
    r1 = await client.post("/api/jobs", json={"category": "abaya boutiques", "depth": 1})
    assert r1.json()["job"]["vertical_tag"] == "abaya"
    r2 = await client.post("/api/jobs", json={"category": "dental clinics", "depth": 1})
    assert r2.json()["job"]["vertical_tag"] == "default"
    r3 = await client.post("/api/jobs", json={"category": "auto parts wholesale", "depth": 1})
    assert r3.json()["job"]["vertical_tag"] == "autoparts_b2b"


async def test_create_job_bad_depth(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client)
    resp = await client.post(
        "/api/jobs", json={"vertical_tag": "abaya", "query": "x", "depth": 9}
    )
    assert resp.status_code == 400


async def test_list_and_get_job(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("backend.routers.jobs.run_scrape_job", lambda jid: None)
    await _login(client)
    created = await client.post(
        "/api/jobs", json={"vertical_tag": "fuel", "query": "fuel calicut", "depth": 1}
    )
    jid = created.json()["job"]["id"]

    listing = await client.get("/api/jobs")
    assert any(j["id"] == jid for j in listing.json()["jobs"])

    one = await client.get(f"/api/jobs/{jid}")
    assert one.json()["job"]["query"] == "fuel calicut"


# --- scraper unit tests -----------------------------------------------------
def test_map_record_basic() -> None:
    job = Job(query="q", vertical_tag="abaya", depth=1, city="Dubai", started_by=1)
    rec = {
        "title": "Hessa Boutique",
        "category": "Clothing store",
        "address": "Dubai Marina, UAE",
        "website": "https://hessa.ae",
        "phone": "+971500000000",
        "review_rating": 4.8,
        "review_count": 240,
        "emails": ["hi@hessa.ae"],
    }
    out = scraper.map_record(rec, job)
    assert out["name"] == "Hessa Boutique"
    assert out["rating"] == 4.8
    assert out["email"] == "hi@hessa.ae"
    assert out["country"] == "UAE"


def test_detect_country() -> None:
    assert scraper.detect_country("Shop 3, Riyadh") == "KSA"
    assert scraper.detect_country("Calicut, Kerala") == "India"
    assert scraper.detect_country(None) is None


def test_parse_output_array(tmp_path: Path) -> None:
    p = tmp_path / "out.json"
    p.write_text(json.dumps([{"title": "A"}, {"title": "B"}]))
    assert len(scraper.parse_output(p)) == 2


def test_parse_output_ndjson(tmp_path: Path) -> None:
    p = tmp_path / "out.json"
    p.write_text('{"title": "A"}\n{"title": "B"}\n')
    assert len(scraper.parse_output(p)) == 2


def test_run_scrape_job_missing_binary(monkeypatch) -> None:
    # With demo mode OFF, a missing gosom binary fails cleanly.
    monkeypatch.setattr(scraper.settings, "GOSOM_BIN", "/nonexistent/gosom-binary")
    monkeypatch.setattr(scraper.settings, "SCRAPER_DEMO", False)
    db = SessionLocal()
    try:
        job = Job(query="q", vertical_tag="abaya", depth=1, started_by=1, status="queued")
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()

    scraper.run_scrape_job(jid)

    db = SessionLocal()
    try:
        job = db.get(Job, jid)
        assert job.status == "failed"
        assert "gosom" in (job.error_message or "").lower()
    finally:
        db.close()


def test_run_scrape_job_demo_mode_produces_leads(monkeypatch) -> None:
    # With demo mode ON and no gosom binary, sample leads are generated and scored.
    monkeypatch.setattr(scraper.settings, "GOSOM_BIN", "/nonexistent/gosom-binary")
    monkeypatch.setattr(scraper.settings, "SCRAPER_DEMO", True)
    monkeypatch.setattr(scraper, "score_lead", lambda lead: (7.0, True, "demo"))
    db = SessionLocal()
    try:
        job = Job(query="abaya boutiques", vertical_tag="abaya", depth=1,
                  started_by=1, status="queued", city="Dubai")
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()

    scraper.run_scrape_job(jid)

    db = SessionLocal()
    try:
        job = db.get(Job, jid)
        assert job.status == "done"
        assert job.leads_found >= 5
        assert job.leads_scored == job.leads_found
    finally:
        db.close()


def test_run_scrape_job_inserts_and_scores(monkeypatch) -> None:
    # Fake the gosom run and the scorer so no external calls happen.
    monkeypatch.setattr(
        scraper,
        "run_gosom",
        lambda query, depth, **kw: [
            {"title": "Lead One", "phone": "+971500000010", "review_rating": 4.6,
             "review_count": 120, "website": "https://one.ae", "address": "Dubai"},
            {"title": "Lead Two", "phone": "+971500000011", "review_rating": 3.2,
             "review_count": 10, "address": "Dubai"},
        ],
    )
    monkeypatch.setattr(scraper, "score_lead", lambda lead: (8.0, True, "fit"))

    db = SessionLocal()
    try:
        job = Job(query="abaya dubai", vertical_tag="abaya", depth=1,
                  started_by=1, status="queued", city="Dubai")
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()

    scraper.run_scrape_job(jid)

    db = SessionLocal()
    try:
        job = db.get(Job, jid)
        assert job.status == "done"
        assert job.leads_found == 2
        assert job.leads_scored == 2
        leads = db.query(Lead).filter(Lead.query_used == "abaya dubai").all()
        assert len(leads) == 2
        assert all(lead.status == "pending" for lead in leads)
        assert all(lead.score == 8.0 for lead in leads)
        assert all(lead.whatsapp_url for lead in leads)
    finally:
        db.close()
