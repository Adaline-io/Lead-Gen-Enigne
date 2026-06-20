"""Turn a typed location into precise coordinates (OpenStreetMap Nominatim).

Used so the Find Leads radius actually centers the Google Maps search on a real
point. No API key required; results are cached to stay within Nominatim's
fair-use policy. Degrades to an empty list if the network is unavailable — the
scrape then just uses the typed location as query text.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from functools import lru_cache

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_UA = "Adaline-LeadGen/1.0 (internal sales tool)"


def _short_label(item: dict) -> str:
    """A compact, human label — first few parts of the display name."""
    parts = [p.strip() for p in item.get("display_name", "").split(",") if p.strip()]
    if not parts:
        return item.get("name", "")
    # name + region + country-ish: keep the first part and the last one or two.
    if len(parts) <= 3:
        return ", ".join(parts)
    return ", ".join([parts[0], parts[-2], parts[-1]])


@lru_cache(maxsize=512)
def _geocode_cached(q: str, limit: int) -> tuple:
    params = urllib.parse.urlencode(
        {"format": "jsonv2", "q": q, "limit": limit, "addressdetails": 1}
    )
    req = urllib.request.Request(f"{_NOMINATIM}?{params}", headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ()

    out: list[dict] = []
    for item in data:
        try:
            out.append({
                "label": item.get("display_name", ""),
                "short": _short_label(item),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
            })
        except (KeyError, ValueError, TypeError):
            continue
    return tuple(out)


def geocode(q: str | None, limit: int = 6) -> list[dict]:
    """Return up to ``limit`` matching places for the query (possibly empty)."""
    q = (q or "").strip()
    if len(q) < 3:
        return []
    return list(_geocode_cached(q, limit))
