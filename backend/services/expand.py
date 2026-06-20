"""Expand a typed industry into DISTINCT related industries (not synonyms).

The goal is the whole market ecosystem around an industry — e.g. for "abaya
boutiques" we want modest fashion, hijab stores, kaftan, tailoring, perfume &
oud, textile shops… NOT "abaya store / abaya shop / abaya outlet" (reworded
duplicates). Uses Claude when ANTHROPIC_API_KEY is set; a curated map otherwise.
A synonym filter guarantees each term is a genuinely different category.
"""

from __future__ import annotations

import json
import re

from backend.config import settings
from backend.services.intake import infer_vertical

# Curated *related industries* per known vertical (diverse, not synonyms).
_CURATED: dict[str, list[str]] = {
    "abaya": [
        "modest fashion", "islamic clothing", "hijab store", "kaftan",
        "bridal wear", "tailoring and alterations", "fashion designer",
        "textile shop", "perfume and oud", "fashion accessories", "lingerie",
    ],
    "autoparts_b2b": [
        "car accessories", "tyre shop", "car battery", "lubricant supplier",
        "car workshop", "auto electrical", "car detailing", "vehicle bodyshop",
        "automotive tools", "car audio", "windscreen and glass",
    ],
    "fuel": [
        "lubricant supplier", "convenience store", "car wash", "tyre shop",
        "vehicle service station", "lpg supplier", "transport company",
    ],
    "hospitality": [
        "resort", "restaurant", "cafe", "event venue", "catering service",
        "travel agency", "tour operator", "spa and wellness", "banquet hall",
    ],
}

# Generic business words stripped when comparing two terms for "same core".
_GENERIC = {
    "store", "shop", "boutique", "outlet", "supplier", "company", "service",
    "dealer", "trading", "center", "centre", "agency", "wholesale", "retail",
    "co", "llc", "shops", "stores", "market", "mart", "house", "hub", "and",
}


def _norm_word(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


_GENERIC_SINGULAR = {_norm_word(g) for g in _GENERIC}


def _core(term: str) -> str:
    """Reduce a term to its distinguishing words (drop generic business words)."""
    words = re.sub(r"[^a-z0-9 ]", " ", term.lower()).split()
    keep = [_norm_word(w) for w in words if _norm_word(w) not in _GENERIC_SINGULAR]
    return " ".join(keep).strip()


def _distinct(base: str, terms: list[str], max_terms: int) -> list[str]:
    """Keep base first, then only terms with a genuinely different core."""
    base_core = _core(base)
    seen = {base_core}
    out = [base]
    for t in terms:
        t = t.strip()
        c = _core(t)
        if not c or c in seen:
            continue          # drops synonyms of the base and of each other
        seen.add(c)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def _heuristic(base: str, max_terms: int) -> list[str]:
    vertical = infer_vertical(base)
    related = _CURATED.get(vertical, [])
    return _distinct(base, related, max_terms)


def _claude(base: str, keywords: str | None, max_terms: int) -> list[str] | None:
    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY in (
        "", "test-key", "sk-ant-...",
    ):
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = (
            "You build B2B prospect lists. For the industry "
            f'"{base}"' + (f" (context: {keywords})" if keywords else "")
            + ", list the DISTINCT but related business categories that make up "
            "its broader market ecosystem — businesses it sits alongside, "
            "supplies, sells to, or competes with in adjacent niches.\n\n"
            "STRICT RULES:\n"
            "- Each item must be a DIFFERENT category, NOT a synonym or reworded "
            f'version of "{base}". For "coffee shops" → cafes, roasteries, '
            'bakeries, dessert parlours, tea houses — NOT "coffee store", '
            '"coffee outlet".\n'
            "- Use short, searchable category names (2-4 words).\n"
            f"- Return ONLY a JSON array of up to {max_terms} strings.\n"
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
        return _distinct(base, terms, max_terms)
    except Exception:
        return None


def expand_queries(
    base: str, keywords: str | None = None, max_terms: int = 10
) -> list[str]:
    """Return the base industry plus DISTINCT related industries (deduped)."""
    base = (base or "").strip()
    if not base:
        return []
    return _claude(base, keywords, max_terms) or _heuristic(base, max_terms)
