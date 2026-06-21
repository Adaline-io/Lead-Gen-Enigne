"""WhatsApp deep-link generation and phone normalization (CLAUDE.md §9, §14).

Always uses the ``https://wa.me/{digits}?text=...`` form — never the
``whatsapp://`` URI scheme (broken on iOS Safari, standing rule #7).
"""

from __future__ import annotations

import re
from urllib.parse import quote

# Per-vertical opening messages. {name}/{city} are filled in; {rep} is the
# assigned sales rep's name (so the message is signed by whoever works the lead).
# The rep personalizes the rest before sending.
TEMPLATES: dict[str, str] = {
    "abaya": (
        "Hi! Saw {name} — really like the brand. We're Adaline, a brand "
        "and content studio in Calicut working with abaya labels across "
        "the GCC. Currently working with ALIFA (Dubai). Open to a quick "
        "15-min conversation?\n\n— {rep}, Adaline"
    ),
    "autoparts_b2b": (
        "Hi! Came across {name} — looks like a serious operation in {city}. "
        "We're Adaline, building digital systems for auto-parts distributors "
        "in the GCC. Currently working with Roca Group on Saudi expansion. "
        "Open to a peer call?\n\n— {rep}, Adaline (Calicut)"
    ),
    "fuel": (
        "Hi! Saw {name} on Google. We're Adaline, running a 36-month brand "
        "programme with Roca Fuels (MRPL dealer in Calicut) — websites, "
        "content, customer engagement. Open to a quick walk-through of "
        "what's working?\n\n— {rep}, Adaline"
    ),
    "hospitality": (
        "Hi! Came across {name} — love the look. We're Adaline, a brand "
        "studio in Calicut working with boutique hospitality on identity, "
        "photography, and direct-booking websites. Open to a quick chat "
        "if direct-channel growth is on your radar?\n\n— {rep}, Adaline"
    ),
    "default": (
        "Hi! Came across {name} on Google. We're Adaline, a brand and tech "
        "studio in Calicut working with premium businesses across Kerala "
        "and the Gulf. Open to a short conversation about what we do?\n\n— {rep}, Adaline"
    ),
}

# Signature fallback when a lead isn't assigned to anyone yet.
DEFAULT_REP = "Aslam"

# Country field / detected-country -> dialing code.
_COUNTRY_CODES: dict[str, str] = {
    "UAE": "971",
    "KSA": "966",
    "SAUDI ARABIA": "966",
    "QATAR": "974",
    "BAHRAIN": "973",
    "OMAN": "968",
    "KUWAIT": "965",
    "INDIA": "91",
}

# Prefixes that mean the number is already international.
_INTL_PREFIXES = ("971", "966", "974", "973", "968", "965", "91")


def normalize_phone(raw: str | None, country: str | None) -> str:
    """Strip non-digits and ensure a country code. Returns digits only."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""

    # Drop a leading international "00" trunk prefix.
    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith(_INTL_PREFIXES):
        return digits

    # Local number: strip a single leading zero, then prepend country code.
    local = digits.lstrip("0")
    code = _COUNTRY_CODES.get((country or "").strip().upper(), "")
    if code:
        return code + local
    return digits  # unknown country — return what we have


def build_message(
    name: str | None,
    city: str | None,
    vertical_tag: str,
    rep_name: str | None = None,
) -> str:
    template = TEMPLATES.get(vertical_tag, TEMPLATES["default"])
    return template.format(
        name=name or "your business",
        city=city or "your area",
        rep=(rep_name or DEFAULT_REP).strip() or DEFAULT_REP,
    )


def whatsapp_url(
    phone: str | None,
    country: str | None,
    name: str | None,
    city: str | None,
    vertical_tag: str,
    rep_name: str | None = None,
) -> str | None:
    digits = normalize_phone(phone, country)
    if not digits:
        return None
    text = quote(build_message(name, city, vertical_tag, rep_name))
    return f"https://wa.me/{digits}?text={text}"
