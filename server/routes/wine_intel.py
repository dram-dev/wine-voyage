"""Score comparison, market valuation, and "you may also like".

Scores from real providers are ranked above the model's own estimate and every
row carries `source_kind`, so the UI can label an estimate as an estimate. See
server/score_providers.py for how to plug a licensed data source in.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.db import get_pool
from server.score_providers import (
    SCORE_PROVIDERS,
    VALUATION_PROVIDERS,
    has_live_scores,
    has_live_valuations,
)
from server.sommelier_client import cache_get, cache_set, call_sommelier
from server.valuation import VALUATION_ORDER, store_valuations
from server.wine_identity import WINE_COLUMNS, display_name, serialize_wine, to_float

router = APIRouter(tags=["wine-intel"])

AI_SCORE_SOURCE = "Claude estimate"
AI_VALUE_SOURCE = "Claude estimate"
SCORE_DISCLAIMER = (
    "Estimated from the model's knowledge of the wine and vintage, not a "
    "published score. Treat it as a starting point, not a citation."
)
VALUE_DISCLAIMER = (
    "Estimated retail range, not a live market quote. Auction and retail "
    "prices move; confirm before insuring or selling."
)
class RecommendRequest(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    cellar_id: Optional[int] = Field(default=None, ge=1)
    count: int = Field(default=8, ge=1, le=20)
    price_ceiling: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=500, description="Steer it: 'for a steak dinner', 'under $40'")


@router.get("/wines/{wine_id}/scores")
async def wine_scores(
    wine_id: int,
    refresh: bool = Query(default=False, description="Re-fetch even if scores are stored"),
) -> dict:
    """Every score we hold for a wine, best source first."""
    pool = get_pool()
    wine = await _load_wine(pool, wine_id)

    stored = await _stored_scores(pool, wine_id)
    if stored and not refresh:
        return _score_response(wine, stored)

    fetched = await _fetch_scores(wine)
    if fetched:
        await _store_scores(pool, wine_id, fetched)
    return _score_response(wine, await _stored_scores(pool, wine_id))


@router.get("/wines/{wine_id}/valuation")
async def wine_valuation(
    wine_id: int,
    refresh: bool = Query(default=False),
) -> dict:
    """Current per-bottle value range for a wine."""
    pool = get_pool()
    wine = await _load_wine(pool, wine_id)

    stored = await _stored_valuations(pool, wine_id)
    if stored and not refresh:
        return _valuation_response(wine, stored)

    fetched = await fetch_valuations(wine)
    if fetched:
        await store_valuations(pool, wine_id, fetched)
    return _valuation_response(wine, await _stored_valuations(pool, wine_id))


@router.get("/wines/{wine_id}/similar")
async def similar_wines(
    wine_id: int,
    account_id: Optional[str] = Query(default=None, max_length=128),
    count: int = Query(default=8, ge=1, le=20),
) -> dict:
    """"You may also like" for a single wine.

    Suggestions come from the model; each one is then checked against the
    account's own cellars so the UI can say "you already have this".
    """
    pool = get_pool()
    wine = await _load_wine(pool, wine_id)
    w = serialize_wine(wine)

    cache_key = f"similar:{wine_id}:{count}"
    cached = await cache_get(pool, cache_key)
    if cached is None:
        varietals = ", ".join(w["varietals"]) or "unspecified grapes"
        origin = ", ".join(filter(None, [w["appellation"], w["region"], w["country"]])) or "unknown origin"
        prompt = (
            f"A drinker enjoys {w['display_name']} — {varietals} from {origin}.\n\n"
            f"Suggest {count} other wines they would likely enjoy. Vary the price points and "
            "include at least two from a different region than the reference wine. "
            "Return JSON in this exact shape:\n"
            '{"suggestions": [{"producer": "...", "wine_name": "...", "varietals": ["..."], '
            '"country": "...", "region": "...", "wine_type": "red|white|rose|sparkling|dessert|fortified|other", '
            '"typical_price_usd": 45, "because": "one sentence on why it follows from the reference wine"}]}'
        )
        cached = await call_sommelier(prompt, max_tokens=2048)
        if "error" not in cached:
            await cache_set(pool, cache_key, cached)

    if "error" in cached:
        raise HTTPException(status_code=502, detail=f"recommendation failed: {cached['error']}")

    suggestions = await _mark_owned(pool, cached.get("suggestions") or [], account_id)
    return {"wine": w, "suggestions": suggestions}


@router.post("/recommendations")
async def cellar_recommendations(req: RecommendRequest) -> dict:
    """"You may also like", informed by the whole cellar plus the saved taste profile.

    Reads the account's top producers, varietals, and regions, hands that
    profile to the sommelier, and filters out anything already owned.
    """
    pool = get_pool()

    where = "c.account_id = $1" + (" AND b.cellar_id = $2" if req.cellar_id else "")
    params: list = [req.account_id] + ([req.cellar_id] if req.cellar_id else [])

    holdings, varietal_rows, taste_rows = await asyncio.gather(
        pool.fetch(
            f"""
            SELECT w.producer, w.wine_name, w.vintage, w.region, w.country,
                   SUM(b.quantity) AS bottles, AVG(b.my_rating) AS my_rating
              FROM cellar_bottles b
              JOIN cellars c ON c.id = b.cellar_id
              JOIN wines   w ON w.id = b.wine_id
             WHERE {where} AND b.status = 'in_cellar' AND b.quantity > 0
             GROUP BY 1, 2, 3, 4, 5
             ORDER BY my_rating DESC NULLS LAST, bottles DESC
             LIMIT 40
            """,
            *params,
        ),
        pool.fetch(
            f"""
            SELECT varietal, SUM(b.quantity) AS bottles
              FROM cellar_bottles b
              JOIN cellars c ON c.id = b.cellar_id
              JOIN wines   w ON w.id = b.wine_id
              CROSS JOIN LATERAL unnest(w.varietals) AS varietal
             WHERE {where} AND b.status = 'in_cellar' AND b.quantity > 0
             GROUP BY 1 ORDER BY bottles DESC LIMIT 12
            """,
            *params,
        ),
        pool.fetch("SELECT name, region, grape, notes FROM taste_profile ORDER BY id LIMIT 20"),
    )

    if not holdings and not taste_rows:
        raise HTTPException(
            status_code=400,
            detail="add a few bottles or taste-profile entries first — there's nothing to reason from",
        )

    holding_lines = "\n".join(
        f"- {display_name(h['producer'], h['wine_name'], h['vintage'])}"
        + (f" ({h['region'] or h['country']})" if h["region"] or h["country"] else "")
        + f" x{h['bottles']}"
        + (f", rated {to_float(h['my_rating']):.0f}/100" if h["my_rating"] is not None else "")
        for h in holdings
    ) or "(cellar is empty)"
    varietal_line = ", ".join(f"{r['varietal']} ({r['bottles']})" for r in varietal_rows) or "none recorded"
    taste_line = "\n".join(
        f"- {t['name']}"
        + (f" ({t['region']})" if t["region"] else "")
        + (f", {t['grape']}" if t["grape"] else "")
        + (f" — {t['notes']}" if t["notes"] else "")
        for t in taste_rows
    ) or "(none saved)"

    budget = f"Keep every suggestion at or under ${req.price_ceiling:.0f} per bottle. " if req.price_ceiling else ""
    steer = f"The drinker adds: {req.note.strip()}. " if req.note else ""

    prompt = (
        f"Cellar contents (most-loved first):\n{holding_lines}\n\n"
        f"Varietals by volume: {varietal_line}\n\n"
        f"Reference winemakers from their taste profile:\n{taste_line}\n\n"
        f"{budget}{steer}"
        f"Suggest {req.count} wines to buy next. Build on what they already drink but do not "
        "suggest a wine already listed above. Cover a mix: at least two that extend a region "
        "they clearly love, at least two that open a region they are missing, and at least one "
        "value bottle. Return JSON in this exact shape:\n"
        '{"suggestions": [{"producer": "...", "wine_name": "...", "varietals": ["..."], '
        '"country": "...", "region": "...", "wine_type": "red|white|rose|sparkling|dessert|fortified|other", '
        '"typical_price_usd": 45, "because": "one sentence tied to a specific bottle they own"}]}'
    )

    digest = hashlib.sha256(
        json.dumps(
            {
                "h": [f"{h['producer']}|{h['wine_name']}|{h['vintage']}" for h in holdings],
                "n": req.count,
                "p": req.price_ceiling,
                "note": (req.note or "").strip().lower(),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache_key = f"recommend:{digest}"

    response = await cache_get(pool, cache_key)
    if response is None:
        response = await call_sommelier(prompt, max_tokens=3000)
        if "error" not in response:
            await cache_set(pool, cache_key, response)
    if "error" in response:
        raise HTTPException(status_code=502, detail=f"recommendation failed: {response['error']}")

    suggestions = await _mark_owned(pool, response.get("suggestions") or [], req.account_id)
    return {
        "based_on": {
            "bottle_lots": len(holdings),
            "top_varietals": [r["varietal"] for r in varietal_rows[:5]],
            "taste_profile_entries": len(taste_rows),
        },
        "suggestions": suggestions,
    }


async def _load_wine(pool, wine_id: int):
    wine = await pool.fetchrow(f"SELECT {WINE_COLUMNS} FROM wines WHERE id = $1", wine_id)
    if wine is None:
        raise HTTPException(status_code=404, detail="wine not found")
    return wine


async def _stored_scores(pool, wine_id: int) -> list:
    return await pool.fetch(
        """
        SELECT source, source_kind, score, scale, reviewer, review, url, confidence, fetched_at
          FROM wine_scores
         WHERE wine_id = $1
         ORDER BY CASE source_kind WHEN 'critic' THEN 0 WHEN 'community' THEN 1 ELSE 2 END,
                  score DESC NULLS LAST
        """,
        wine_id,
    )


async def _stored_valuations(pool, wine_id: int) -> list:
    return await pool.fetch(
        """
        SELECT source, source_kind, low, mid, high, currency, note, confidence, fetched_at
          FROM wine_valuations
         WHERE wine_id = $1
         ORDER BY {VALUATION_ORDER}
        """.format(VALUATION_ORDER=VALUATION_ORDER),
        wine_id,
    )


async def _fetch_scores(wine) -> list[dict]:
    """Live providers first; the AI estimate only fills the gap they leave."""
    w = serialize_wine(wine)
    if SCORE_PROVIDERS:
        results = await asyncio.gather(
            *(p.fetch(w) for p in SCORE_PROVIDERS), return_exceptions=True
        )
        rows = [row for r in results if isinstance(r, list) for row in r]
        if rows:
            return rows

    origin = ", ".join(filter(None, [w["appellation"], w["region"], w["country"]])) or "unknown origin"
    prompt = (
        f"Wine: {w['display_name']} ({origin}).\n\n"
        "Give your best estimate of how the major critics score this wine and vintage, on the "
        "100-point scale, plus a one-paragraph tasting impression. If you do not know this wine "
        'well, say so with a low confidence. Return JSON in this exact shape:\n'
        '{"score": 93.0, "confidence": 0.6, "review": "...", '
        '"critic_range": {"low": 90, "high": 95}, '
        '"drink_from": 2026, "drink_to": 2040}'
    )
    response = await call_sommelier(prompt, max_tokens=1200)
    if "error" in response or response.get("score") is None:
        return []
    return [
        {
            "source": AI_SCORE_SOURCE,
            "source_kind": "ai_estimate",
            "score": _num(response.get("score"), 0, 100),
            "scale": "100",
            "reviewer": None,
            "review": response.get("review"),
            "url": None,
            "confidence": _num(response.get("confidence"), 0, 1),
        }
    ]


async def fetch_valuations(wine) -> list[dict]:
    w = serialize_wine(wine)
    if VALUATION_PROVIDERS:
        results = await asyncio.gather(
            *(p.fetch(w) for p in VALUATION_PROVIDERS), return_exceptions=True
        )
        rows = [r for r in results if isinstance(r, dict)]
        if rows:
            return rows

    origin = ", ".join(filter(None, [w["appellation"], w["region"], w["country"]])) or "unknown origin"
    prompt = (
        f"Wine: {w['display_name']} ({origin}), {w['bottle_size_ml']}ml.\n\n"
        "Estimate the current per-bottle market price in USD — the range a buyer would actually "
        "pay at retail or auction today. Return JSON in this exact shape:\n"
        '{"low": 60, "mid": 85, "high": 120, "currency": "USD", "confidence": 0.5, '
        '"note": "one sentence on what drives the range"}'
    )
    response = await call_sommelier(prompt, max_tokens=800)
    if "error" in response or response.get("mid") is None:
        return []
    return [
        {
            "source": AI_VALUE_SOURCE,
            "source_kind": "ai_estimate",
            "low": _num(response.get("low"), 0, 10_000_000),
            "mid": _num(response.get("mid"), 0, 10_000_000),
            "high": _num(response.get("high"), 0, 10_000_000),
            "currency": (response.get("currency") or "USD")[:3].upper(),
            "note": response.get("note"),
            "confidence": _num(response.get("confidence"), 0, 1),
        }
    ]


async def _store_scores(pool, wine_id: int, rows: list[dict]) -> None:
    await pool.executemany(
        """
        INSERT INTO wine_scores (wine_id, source, source_kind, score, scale, reviewer, review, url, confidence)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (wine_id, source) DO UPDATE SET
            source_kind = EXCLUDED.source_kind, score = EXCLUDED.score, scale = EXCLUDED.scale,
            reviewer = EXCLUDED.reviewer, review = EXCLUDED.review, url = EXCLUDED.url,
            confidence = EXCLUDED.confidence, fetched_at = NOW()
        """,
        [
            (
                wine_id, r["source"], r["source_kind"], r.get("score"), r.get("scale", "100"),
                r.get("reviewer"), r.get("review"), r.get("url"), r.get("confidence"),
            )
            for r in rows
        ],
    )


def _score_response(wine, rows) -> dict:
    scores = [
        {
            "source": r["source"],
            "source_kind": r["source_kind"],
            "score": to_float(r["score"]),
            "scale": r["scale"],
            "reviewer": r["reviewer"],
            "review": r["review"],
            "url": r["url"],
            "confidence": to_float(r["confidence"]),
            "estimated": r["source_kind"] == "ai_estimate",
            "fetched_at": r["fetched_at"].isoformat(),
        }
        for r in rows
    ]
    hundred_point = [s["score"] for s in scores if s["score"] is not None and s["scale"] == "100"]
    return {
        "wine": serialize_wine(wine),
        "scores": scores,
        "consensus": round(sum(hundred_point) / len(hundred_point), 1) if hundred_point else None,
        "best": scores[0] if scores else None,
        "has_live_sources": has_live_scores(),
        "disclaimer": None if has_live_scores() else SCORE_DISCLAIMER,
    }


def _valuation_response(wine, rows) -> dict:
    valuations = [
        {
            "source": r["source"],
            "source_kind": r["source_kind"],
            "low": to_float(r["low"]),
            "mid": to_float(r["mid"]),
            "high": to_float(r["high"]),
            "currency": r["currency"],
            "note": r["note"],
            "confidence": to_float(r["confidence"]),
            "estimated": r["source_kind"] == "ai_estimate",
            "fetched_at": r["fetched_at"].isoformat(),
        }
        for r in rows
    ]
    return {
        "wine": serialize_wine(wine),
        "valuations": valuations,
        "best": valuations[0] if valuations else None,
        "has_live_sources": has_live_valuations(),
        "disclaimer": None if has_live_valuations() else VALUE_DISCLAIMER,
    }


async def _mark_owned(pool, suggestions: list, account_id: Optional[str]) -> list[dict]:
    """Flag suggestions the account already holds, so the UI can grey them out."""
    clean = [s for s in suggestions if isinstance(s, dict) and s.get("producer")]
    if not clean or not account_id:
        return clean

    producers = [str(s["producer"]) for s in clean]
    owned = await pool.fetch(
        """
        SELECT DISTINCT lower(w.producer) AS producer
          FROM cellar_bottles b
          JOIN cellars c ON c.id = b.cellar_id
          JOIN wines   w ON w.id = b.wine_id
         WHERE c.account_id = $1 AND b.status = 'in_cellar' AND b.quantity > 0
           AND lower(w.producer) = ANY($2::text[])
        """,
        account_id, [p.lower() for p in producers],
    )
    owned_set = {r["producer"] for r in owned}
    return [{**s, "already_owned": str(s["producer"]).lower() in owned_set} for s in clean]


def _num(value, low: float, high: float) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if low <= number <= high else None
