"""Tests for the deterministic, data-driven quality scoring engine."""

from __future__ import annotations

from backend.models import Lead
from backend.services.quality import compute_quality


def _lead(**kw) -> Lead:
    base = dict(name="X", vertical_tag="default", country="UAE")
    base.update(kw)
    return Lead(**base)


# --- abaya rubric ----------------------------------------------------------
def test_abaya_premium_brand_scores_high() -> None:
    lead = _lead(
        name="Hessa Boutique", vertical_tag="abaya", city="Dubai Marina",
        address="Marina Walk, Dubai Marina, UAE", country="UAE",
        rating=4.8, review_count=240, website="https://hessa.ae",
    )
    score, qualified, reason = compute_quality(lead)
    assert score >= 8.0 and qualified is True
    # Reason summarises the data signals (no region tag / tier label).
    assert "reviews" in reason and "site" in reason
    assert "GCC" not in reason and "qualified" not in reason


def test_abaya_commodity_name_penalised() -> None:
    lead = _lead(
        name="Al Wahda General Trading", vertical_tag="abaya",
        city="Sharjah", address="Industrial, Sharjah, UAE", country="UAE",
        rating=3.2, review_count=28, website=None,
    )
    score, qualified, _ = compute_quality(lead)
    assert score < 5.0 and qualified is False


def test_abaya_outside_gcc_skipped() -> None:
    lead = _lead(
        name="Noor Abaya", vertical_tag="abaya", city="London",
        address="Oxford St, London", country="UK",
        rating=4.7, review_count=200, website="https://noor.com",
    )
    score, qualified, _ = compute_quality(lead)
    assert qualified is False  # we serve the GCC abaya market


def test_abaya_midtier_single_outlet() -> None:
    lead = _lead(
        name="Layali Boutique", vertical_tag="abaya", city="Ajman",
        address="Ajman, UAE", country="UAE",
        rating=4.1, review_count=55, website="https://layali.ae",
    )
    score, qualified, _ = compute_quality(lead)
    assert 5.0 <= score < 8.0 and qualified is True


# --- autoparts rubric ------------------------------------------------------
def test_autoparts_wholesale_in_industrial_zone_high() -> None:
    lead = _lead(
        name="Gulf Spare Parts Wholesale", vertical_tag="autoparts_b2b",
        city="Riyadh", address="2nd Industrial City, Riyadh", country="KSA",
        rating=4.6, review_count=120, website="https://gulfparts.sa",
    )
    score, qualified, _ = compute_quality(lead)
    assert score >= 8.0 and qualified is True


def test_autoparts_service_garage_rejected() -> None:
    lead = _lead(
        name="QuickLube Car Wash & Garage", vertical_tag="autoparts_b2b",
        city="Dubai", address="Dubai", country="UAE",
        rating=4.0, review_count=200, website=None,
    )
    score, qualified, _ = compute_quality(lead)
    assert qualified is False  # they buy from distributors — wrong fit


# --- default rubric --------------------------------------------------------
def test_default_conservative() -> None:
    weak = _lead(name="Some Shop", vertical_tag="fuel", country="India",
                 city="Kochi", rating=3.5, review_count=10, website=None)
    score, qualified, _ = compute_quality(weak)
    assert qualified is False

    strong = _lead(name="Roca Fuels", vertical_tag="fuel", country="India",
                   city="Calicut", address="Calicut, Kerala",
                   rating=4.6, review_count=320, website="https://rocafuels.in")
    s2, q2, _ = compute_quality(strong)
    assert s2 >= 7.0 and q2 is True


def test_qualified_threshold_is_five() -> None:
    lead = _lead(name="Edge", vertical_tag="default", country="UAE",
                 rating=4.5, review_count=50, website=None)
    score, qualified, _ = compute_quality(lead)
    assert qualified == (score >= 5.0)


def test_no_data_scores_low() -> None:
    lead = _lead(name="Unknown", vertical_tag="abaya", country=None)
    score, qualified, reason = compute_quality(lead)
    assert score < 5.0 and qualified is False
    assert reason  # always explainable
