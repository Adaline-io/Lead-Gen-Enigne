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
    # The search query is the industry only — keywords are a post-scrape filter.
    assert job["query"] == "abaya boutique"
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
    # A missing gosom binary fails cleanly (no demo fallback — real data only).
    monkeypatch.setattr(scraper.settings, "GOSOM_BIN", "/nonexistent/gosom-binary")
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


def test_run_scrape_job_parses_real_output(monkeypatch, tmp_path) -> None:
    # With a real gosom output file, leads are inserted and scored — no demo.
    records = [
        {"title": "Acme Clothing Kozhikode", "category": "Clothing",
         "address": "Kozhikode, Kerala, India", "phone": "+919876543210",
         "website": "https://acme.example.in", "review_rating": 4.6,
         "review_count": 410},
        {"title": "Beta Apparel Kozhikode", "category": "Clothing",
         "address": "Kozhikode, Kerala, India", "phone": "+919812345678",
         "website": "https://beta.example.in", "review_rating": 4.3,
         "review_count": 95},
    ]
    monkeypatch.setattr(scraper, "run_gosom", lambda *a, **k: list(records))
    monkeypatch.setattr(scraper, "score_lead", lambda lead: (7.0, True, "ok"))
    db = SessionLocal()
    try:
        job = Job(query="clothing brand", vertical_tag="default", depth=1,
                  started_by=1, status="queued", city="Kozhikode")
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
        assert job.leads_scored == job.leads_found
    finally:
        db.close()


def test_build_enrichment_captures_cold_call_fields() -> None:
    rec = {
        "title": "North Republic",
        "link": "https://maps.google.com/place/x",
        "open_hours": {"Monday": ["10 am–10:30 pm"], "Friday": ["10 am–12 am"]},
        "owner": {"id": "1", "name": "North Republic Mgmt"},
        "price_range": "₹₹",
        "plus_code": "7Q5P+C6",
        "latitude": 11.25, "longitude": 75.78,
    }
    enr = scraper.build_enrichment(rec)
    assert enr["maps_url"] == "https://maps.google.com/place/x"
    assert "Mon 10 am–10:30 pm" in enr["hours"]
    assert enr["owner"] == "North Republic Mgmt"
    assert enr["price_range"] == "₹₹"
    assert enr["plus_code"] == "7Q5P+C6"
    assert enr["lat"] == 11.25 and enr["lng"] == 75.78
    assert isinstance(enr["hours_by_day"], dict)


def test_build_enrichment_owner_from_json_string() -> None:
    # gosom's CSV output gives `owner` as a JSON string, not a dict.
    enr = scraper.build_enrichment(
        {"title": "X", "owner": '{"id":"1","name":"Shop Mgmt"}'}
    )
    assert enr["owner"] == "Shop Mgmt"


def test_map_record_stores_enrichment_json() -> None:
    job = Job(query="x", vertical_tag="default", depth=1, started_by=1)
    fields = scraper.map_record(
        {"title": "Shop", "phone": "+97150", "owner": {"name": "Owner A"},
         "open_hours": {"Monday": ["9–5"]}}, job
    )
    assert "enrichment" in fields
    enr = json.loads(fields["enrichment"])
    assert enr["owner"] == "Owner A"


def test_keep_useful_drops_junk_rows() -> None:
    recs = [
        {"title": "Has Phone", "phone": "+971500000001"},
        {"title": "Has Email", "emails": ["x@y.ae"]},
        {"title": "Has Website", "website": "https://z.ae"},
        {"title": "Has Address", "address": "Dubai Marina"},
        {"title": "Junk Row With No Contact Data"},        # dropped
        {"title": "Blank Phone", "phone": "  ", "website": ""},  # dropped
    ]
    kept = scraper.keep_useful(recs)
    titles = {r["title"] for r in kept}
    assert "Junk Row With No Contact Data" not in titles
    assert "Blank Phone" not in titles
    assert len(kept) == 4  # all real leads kept


def test_filter_by_keywords() -> None:
    recs = [
        {"title": "Premium Abaya House", "category": "abaya boutique"},
        {"title": "Budget Cloth Store", "category": "abaya boutique"},
        {"title": "Luxury Atelier", "category": "fashion", "website": "premium.ae"},
    ]
    # No keywords → everything passes through.
    assert scraper.filter_by_keywords(recs, None) == recs
    # Single keyword matches name or website.
    kept = scraper.filter_by_keywords(recs, "premium")
    assert {r["title"] for r in kept} == {"Premium Abaya House", "Luxury Atelier"}
    # Comma/space separated keywords are OR-ed.
    kept2 = scraper.filter_by_keywords(recs, "budget, luxury")
    assert {r["title"] for r in kept2} == {"Budget Cloth Store", "Luxury Atelier"}


def test_run_scrape_job_filters_on_keywords(monkeypatch) -> None:
    monkeypatch.setattr(
        scraper,
        "run_gosom",
        lambda query, depth, **kw: [
            {"title": "Premium Abaya House", "phone": "+971500000020",
             "category": "premium abaya", "address": "Dubai"},
            {"title": "Cheap Cloth Shop", "phone": "+971500000021",
             "category": "abaya", "address": "Dubai"},
        ],
    )
    monkeypatch.setattr(scraper, "score_lead", lambda lead: (7.0, True, "fit"))

    db = SessionLocal()
    try:
        job = Job(query="abaya", vertical_tag="abaya", depth=1, started_by=1,
                  status="queued", city="Dubai", keywords="premium")
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
        assert job.leads_found == 1  # only the 'premium' row survived the filter
    finally:
        db.close()


def test_run_scrape_job_marks_failed_not_stuck(monkeypatch) -> None:
    # A failure during insert/score must mark the job 'failed', never leave it
    # hanging on 'running' (which shows as an endless spinner in the UI).
    monkeypatch.setattr(scraper, "run_gosom", lambda query, depth, **kw: [
        {"title": "X", "phone": "+97150", "address": "Dubai"},
    ])

    def boom(*a, **k):
        raise RuntimeError("simulated DB failure")

    monkeypatch.setattr(scraper, "_insert_leads", boom)

    db = SessionLocal()
    try:
        job = Job(query="abaya", vertical_tag="abaya", depth=1, started_by=1,
                  status="queued", city="Dubai")
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
        assert "simulated DB failure" in (job.error_message or "")
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
