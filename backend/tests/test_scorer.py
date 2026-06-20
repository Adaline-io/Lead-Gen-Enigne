"""Scorer parsing + fallback behaviour (no real API calls)."""

from __future__ import annotations

from backend.models import Lead
from backend.services import scorer
from backend.services.whatsapp import normalize_phone, whatsapp_url


def test_parse_valid_json() -> None:
    out = scorer._parse('{"score": 7.5, "qualified": true, "reason": "good fit"}')
    assert out == (7.5, True, "good fit")


def test_parse_json_with_preamble() -> None:
    text = 'Here you go:\n{"score": 3.0, "qualified": false, "reason": "skip"}\nthanks'
    assert scorer._parse(text) == (3.0, False, "skip")


def test_parse_infers_qualified_from_score() -> None:
    score, qualified, _ = scorer._parse('{"score": 6.0, "reason": "x"}')
    assert score == 6.0 and qualified is True


def test_parse_garbage_returns_none() -> None:
    assert scorer._parse("no json here") is None


def test_score_lead_without_key_uses_data_driven(monkeypatch) -> None:
    # With no API key, scoring falls back to the deterministic engine and still
    # produces a real score from the lead's own data.
    monkeypatch.setattr(scorer.settings, "ANTHROPIC_API_KEY", "")
    strong = Lead(
        name="Hessa Boutique", vertical_tag="abaya", city="Dubai Marina",
        address="Dubai Marina, UAE", country="UAE", rating=4.8,
        review_count=240, website="https://hessa.ae",
    )
    score, qualified, reason = scorer.score_lead(strong)
    assert score is not None and score >= 8.0
    assert qualified is True
    assert "scoring error" not in reason


def test_score_lead_falls_back_when_claude_errors(monkeypatch) -> None:
    monkeypatch.setattr(scorer.settings, "ANTHROPIC_API_KEY", "sk-ant-real")

    def _boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(scorer, "_get_client", _boom)
    lead = Lead(name="Hessa", vertical_tag="abaya", country="UAE", rating=4.6, review_count=120, website="https://x.ae")
    score, qualified, _ = scorer.score_lead(lead)
    assert score is not None and qualified is True  # data-driven fallback


def test_score_lead_with_mocked_client(monkeypatch) -> None:
    monkeypatch.setattr(scorer.settings, "ANTHROPIC_API_KEY", "sk-ant-real")

    class _Block:
        type = "text"
        text = '{"score": 9.1, "qualified": true, "reason": "premium"}'

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            return _Resp()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(scorer, "_get_client", lambda: _Client())
    lead = Lead(name="Hessa", vertical_tag="abaya", city="Dubai")
    assert scorer.score_lead(lead) == (9.1, True, "premium")


def test_load_prompt_falls_back_to_default() -> None:
    text = scorer.load_prompt("nonexistent_vertical")
    assert "B2B lead-qualification analyst" in text


# --- whatsapp ---------------------------------------------------------------
def test_normalize_phone_local_uae() -> None:
    assert normalize_phone("050 123 4567", "UAE") == "971501234567"


def test_normalize_phone_already_intl() -> None:
    assert normalize_phone("+971 50 123 4567", "UAE") == "971501234567"


def test_normalize_phone_india() -> None:
    assert normalize_phone("0 98470 12345", "India") == "919847012345"


def test_whatsapp_url_shape() -> None:
    url = whatsapp_url("+971501234567", "UAE", "Hessa", "Dubai", "abaya")
    assert url.startswith("https://wa.me/971501234567?text=")
    assert "%E2%80%94" in url or "Adaline" in url  # encoded em-dash / signature


def test_whatsapp_url_none_without_phone() -> None:
    assert whatsapp_url(None, "UAE", "X", "Dubai", "abaya") is None
