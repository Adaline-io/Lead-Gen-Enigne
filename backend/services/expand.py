"""Expand a typed industry into related Google Maps search terms.

So "abaya boutiques" also catches modest-fashion stores, kaftan shops, etc. —
the whole market, not just the exact phrase. Uses Claude when a key is set
(works for any industry), and falls back to curated + generic expansions.
"""

from __future__ import annotations

import json

from backend.config import settings
from backend.services.intake import infer_vertical

# Curated related categories per known vertical (the base term is added too).
_CURATED: dict[str, list[str]] = {
    "abaya": [
        "abaya boutique", "modest fashion store", "islamic clothing store",
        "kaftan shop", "hijab store", "women's fashion boutique",
        "designer abaya", "jalabiya shop",
    ],
    "autoparts_b2b": [
        "auto parts store", "car spare parts", "auto parts wholesale",
        "automotive parts supplier", "car accessories shop", "tyre shop",
        "auto parts distributor", "vehicle spare parts trading",
    ],
    "fuel": [
        "petrol pump", "fuel station", "gas station", "service station",
        "petroleum dealer", "filling station",
    ],
    "hospitality": [
        "hotel", "resort", "boutique hotel", "guest house",
        "serviced apartments", "bed and breakfast", "lodge",
    ],
}

# Generic morphological expansion for unknown industries.
_GENERIC_SUFFIXES = ("", " store", " shop", " supplier", " services", " company", " dealer")


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _heuristic(base: str, max_terms: int) -> list[str]:
    vertical = infer_vertical(base)
    terms = [base]
    if vertical in _CURATED:
        terms += _CURATED[vertical]
    else:
        head = base.split(" in ")[0].strip()
        terms += [f"{head}{suf}" for suf in _GENERIC_SUFFIXES]
    return _dedup_keep_order(terms)[:max_terms]


def _claude(base: str, keywords: str | None, max_terms: int) -> list[str] | None:
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY in (
        "", "test-key", "sk-ant-...",
    ):
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = (
            "You help a B2B sales team find businesses on Google Maps. "
            f'For the industry/search: "{base}"'
            + (f' (keywords: {keywords})' if keywords else "")
            + ". List closely-related Google Maps search queries — categories, "
            "synonyms, and similar business types — that would surface comparable "
            f"businesses. Return ONLY a JSON array of up to {max_terms} short "
            'search strings (no location). Include the original.'
        )
        resp = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return None
        data = json.loads(text[start : end + 1])
        terms = [str(t) for t in data if str(t).strip()]
        return _dedup_keep_order([base, *terms])[:max_terms] or None
    except Exception:
        return None


def expand_queries(
    base: str, keywords: str | None = None, max_terms: int = 8
) -> list[str]:
    """Return the base term plus related search terms (deduped, capped)."""
    base = (base or "").strip()
    if not base:
        return []
    return _claude(base, keywords, max_terms) or _heuristic(base, max_terms)
