"""Canonical wine identity: normalization, dedupe keys, and row serialization.

Two bottles are "the same wine" when producer, cuvée, vintage, and bottle size
agree once punctuation and casing are stripped. `natural_key` encodes that, and
`upsert_wine` uses it to fold a newly scanned label into an existing `wines` row
— filling in fields the existing row is missing rather than overwriting what is
already known.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import asyncpg

# Bottle formats we recognize by name, in millilitres.
BOTTLE_SIZES: dict[str, int] = {
    "piccolo": 187,
    "half": 375,
    "demi": 375,
    "standard": 750,
    "magnum": 1500,
    "double magnum": 3000,
    "jeroboam": 3000,
    "rehoboam": 4500,
    "methuselah": 6000,
    "imperial": 6000,
    "salmanazar": 9000,
    "balthazar": 12000,
    "nebuchadnezzar": 15000,
}

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(text: Optional[str]) -> str:
    """Fold accents, drop punctuation, collapse whitespace, lowercase.

    "Château Léoville-Barton" and "Chateau Leoville Barton" normalize alike.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _WS.sub(" ", _PUNCT.sub(" ", folded)).strip().lower()


def natural_key(
    producer: str,
    wine_name: Optional[str],
    vintage: Optional[int],
    bottle_size_ml: int = 750,
) -> str:
    return "|".join(
        [
            normalize(producer),
            normalize(wine_name),
            str(vintage) if vintage else "nv",
            str(bottle_size_ml),
        ]
    )


def to_float(value: Any) -> Any:
    """asyncpg hands back Decimal for NUMERIC; JSON wants a plain number."""
    return float(value) if isinstance(value, Decimal) else value


def drink_window_status(
    drink_from: Optional[int],
    drink_to: Optional[int],
    today: Optional[date] = None,
) -> str:
    """One of: unknown, hold, ready, peak_passing, past."""
    if drink_from is None and drink_to is None:
        return "unknown"
    year = (today or date.today()).year
    if drink_from is not None and year < drink_from:
        return "hold"
    if drink_to is not None and year > drink_to:
        return "past"
    if drink_to is not None and year >= drink_to - 1:
        return "peak_passing"
    return "ready"


def serialize_wine(row: asyncpg.Record | dict, prefix: str = "") -> dict:
    """Build the wine half of an API response.

    `prefix` lets a joined query alias wine columns (w_producer, w_vintage, ...)
    without colliding with the bottle's own columns.
    """
    def get(field: str) -> Any:
        return row[f"{prefix}{field}"]

    drink_from, drink_to = get("drink_from"), get("drink_to")
    return {
        "id": get("id"),
        "producer": get("producer"),
        "wine_name": get("wine_name"),
        "vintage": get("vintage"),
        "varietals": list(get("varietals") or []),
        "wine_type": get("wine_type"),
        "country": get("country"),
        "region": get("region"),
        "appellation": get("appellation"),
        "appellation_id": get("appellation_id"),
        "bottle_size_ml": get("bottle_size_ml"),
        "abv": to_float(get("abv")),
        "drink_from": drink_from,
        "drink_to": drink_to,
        "drink_window": drink_window_status(drink_from, drink_to),
        "label_image_url": get("label_image_url"),
        "display_name": display_name(
            get("producer"), get("wine_name"), get("vintage"), get("bottle_size_ml")
        ),
    }


def display_name(
    producer: str,
    wine_name: Optional[str],
    vintage: Optional[int],
    bottle_size_ml: Optional[int] = 750,
) -> str:
    parts = [str(vintage) if vintage else "NV", producer]
    if wine_name:
        parts.append(wine_name)
    label = " ".join(parts)
    if bottle_size_ml and bottle_size_ml != 750:
        label += f" ({format_size(bottle_size_ml)})"
    return label


def format_size(ml: int) -> str:
    for name, size in BOTTLE_SIZES.items():
        if size == ml and name not in ("demi", "imperial"):
            return name.title()
    return f"{ml}ml"


WINE_COLUMNS = """
    id, natural_key, producer, wine_name, vintage, varietals, wine_type,
    country, region, appellation, appellation_id, bottle_size_ml, abv,
    drink_from, drink_to, label_image_url, created_at, updated_at
"""


async def upsert_wine(conn: asyncpg.Connection | asyncpg.Pool, wine: dict) -> asyncpg.Record:
    """Insert a wine, or enrich the existing row with any fields it lacks.

    Scanning a label twice — once from a blurry shot that only caught the
    producer, once from a clean one — should converge on one complete row, so
    the conflict branch fills NULLs rather than overwriting known values.
    """
    key = natural_key(
        wine["producer"], wine.get("wine_name"), wine.get("vintage"), wine.get("bottle_size_ml") or 750
    )
    return await conn.fetchrow(
        f"""
        INSERT INTO wines (
            natural_key, producer, wine_name, vintage, varietals, wine_type,
            country, region, appellation, appellation_id, bottle_size_ml, abv,
            drink_from, drink_to, label_image_url
        )
        VALUES ($1, $2, $3, $4, $5::text[], $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        ON CONFLICT (natural_key) DO UPDATE SET
            varietals       = CASE WHEN cardinality(wines.varietals) = 0
                                   THEN EXCLUDED.varietals ELSE wines.varietals END,
            wine_type       = COALESCE(wines.wine_type, EXCLUDED.wine_type),
            country         = COALESCE(wines.country, EXCLUDED.country),
            region          = COALESCE(wines.region, EXCLUDED.region),
            appellation     = COALESCE(wines.appellation, EXCLUDED.appellation),
            appellation_id  = COALESCE(wines.appellation_id, EXCLUDED.appellation_id),
            abv             = COALESCE(wines.abv, EXCLUDED.abv),
            drink_from      = COALESCE(wines.drink_from, EXCLUDED.drink_from),
            drink_to        = COALESCE(wines.drink_to, EXCLUDED.drink_to),
            label_image_url = COALESCE(wines.label_image_url, EXCLUDED.label_image_url),
            updated_at      = NOW()
        RETURNING {WINE_COLUMNS}
        """,
        key,
        wine["producer"].strip(),
        (wine.get("wine_name") or None),
        wine.get("vintage"),
        [v.strip() for v in (wine.get("varietals") or []) if v and v.strip()],
        wine.get("wine_type"),
        wine.get("country"),
        wine.get("region"),
        wine.get("appellation"),
        wine.get("appellation_id"),
        wine.get("bottle_size_ml") or 750,
        wine.get("abv"),
        wine.get("drink_from"),
        wine.get("drink_to"),
        wine.get("label_image_url"),
    )


def iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
