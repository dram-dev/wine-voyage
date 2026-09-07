"""Defensive coercion of model JSON into wine fields.

The model is told the schema, but a stray string where a number belongs must not
500 a request — anything unparseable becomes null and that field simply goes
unfilled. Shared by the label scanner and the producer lookup, which normalize
the same wine shape from two different prompts.
"""
from __future__ import annotations

from typing import Any, Optional

WINE_TYPES = {"red", "white", "rose", "sparkling", "dessert", "fortified", "other"}

# Things a model writes when it means "I don't know".
NULLISH = {"", "null", "none", "n/a", "na", "unknown", "not visible", "illegible", "unspecified"}


def as_str(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    return None if text.lower() in NULLISH else text


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [s for s in (as_str(v) for v in value) if s]


def as_int(value: Any, low: int, high: int) -> Optional[int]:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def as_float(value: Any, low: float, high: float) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if low <= number <= high else None


def as_enum(value: Any, allowed: set[str]) -> Optional[str]:
    text = as_str(value)
    return text.lower() if text and text.lower() in allowed else None


def wine_fields(payload: dict) -> dict:
    """Coerce a model reply into the shape the add-bottle form expects."""
    wine = {
        "producer": as_str(payload.get("producer")),
        "wine_name": as_str(payload.get("wine_name")),
        "vintage": as_int(payload.get("vintage"), 1800, 2100),
        "varietals": as_str_list(payload.get("varietals"))[:12],
        "wine_type": as_enum(payload.get("wine_type"), WINE_TYPES),
        "country": as_str(payload.get("country")),
        "region": as_str(payload.get("region")),
        "appellation": as_str(payload.get("appellation")),
        "bottle_size_ml": as_int(payload.get("bottle_size_ml"), 50, 30000) or 750,
        "abv": as_float(payload.get("abv"), 0, 100),
        "drink_from": as_int(payload.get("drink_from"), 1800, 2200),
        "drink_to": as_int(payload.get("drink_to"), 1800, 2200),
    }
    # A window that arrives backwards is a transposition, not a reason to drop it.
    if wine["drink_from"] and wine["drink_to"] and wine["drink_from"] > wine["drink_to"]:
        wine["drink_from"], wine["drink_to"] = wine["drink_to"], wine["drink_from"]
    return wine


def value_estimate(payload: Any) -> Optional[dict]:
    """Coerce a {low, mid, high, currency} block, or None if there is no mid."""
    if not isinstance(payload, dict) or payload.get("mid") is None:
        return None
    mid = as_float(payload.get("mid"), 0, 10_000_000)
    if mid is None:
        return None
    return {
        "low": as_float(payload.get("low"), 0, 10_000_000),
        "mid": mid,
        "high": as_float(payload.get("high"), 0, 10_000_000),
        "currency": (as_str(payload.get("currency")) or "USD")[:3].upper(),
        "estimated": True,
    }
