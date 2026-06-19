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


def test_score_lead_without_key_degrades(monkeypatch) -> None:
    monkeypatch.setattr(scorer.settings, "ANTHROPIC_API_KEY", "")
    lead = Lead(name="X", vertical_tag="abaya")
    score, qualified, reason = scorer.score_lead(lead)
    assert score is None and qualified is None
    assert "scoring error" in reason


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
