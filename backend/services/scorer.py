"""Claude-based lead scoring (CLAUDE.md §8).

``score_lead`` returns a ``(score, qualified, reason)`` tuple. It is defensive:
malformed model output is retried once, and a hard failure degrades to
``(None, None, "scoring error: ...")`` rather than raising — a bad score should
never break a scrape run.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.config import settings
from backend.models import Lead

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

ScoreResult = tuple[float | None, bool | None, str]


@lru_cache
def load_prompt(vertical_tag: str) -> str:
    path = PROMPTS_DIR / f"{vertical_tag}.md"
    if not path.exists():
        path = PROMPTS_DIR / "default.md"
    return path.read_text(encoding="utf-8")


def _lead_payload(lead: Lead) -> dict:
    return {
        "name": lead.name,
        "category": lead.category,
        "address": lead.address,
        "city": lead.city,
        "country": lead.country,
        "website": lead.website,
        "phone": lead.phone,
        "rating": lead.rating,
        "review_count": lead.review_count,
    }


def _parse(text: str) -> ScoreResult | None:
    """Pull the first JSON object out of ``text`` and coerce the fields."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start : end + 1])
        score = float(data["score"])
        reason = str(data.get("reason", ""))[:200]
        qualified = bool(data.get("qualified", score >= 5.0))
        return score, qualified, reason
    except (ValueError, KeyError, TypeError):
        return None


def _get_client():
    from anthropic import Anthropic

    return Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def score_lead(lead: Lead) -> ScoreResult:
    """Score a single lead. Never raises — returns a fallback on failure."""
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY in (
        "",
        "test-key",
        "sk-ant-...",
    ):
        return None, None, "scoring error: ANTHROPIC_API_KEY not configured"

    system = load_prompt(lead.vertical_tag)
    user_msg = json.dumps(_lead_payload(lead), ensure_ascii=False)

    try:
        client = _get_client()
        raw = _call(client, system, user_msg)
        parsed = _parse(raw)
        if parsed is None:
            # Retry once, insisting on valid JSON.
            raw = _call(
                client,
                system,
                user_msg + "\n\nRespond with valid JSON only.",
            )
            parsed = _parse(raw)
        if parsed is None:
            return None, None, "scoring error: " + raw[:140]
        return parsed
    except Exception as exc:  # network/auth/etc — degrade, don't crash
        return None, None, f"scoring error: {type(exc).__name__}: {exc}"[:200]


def _call(client, system: str, user_msg: str) -> str:
    resp = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "".join(parts)
