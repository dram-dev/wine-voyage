"""The value tracker: what the cellar is worth, and how that has moved.

Three things live here that the inventory endpoints don't cover:

  * a **total cellar value** report — cost basis vs. current market value,
    unrealized gain, coverage, top movers, and value by region/varietal;
  * **history** — every report writes today's snapshot, so opening the tracker
    is what builds the chart. No cron, no worker;
  * **bulk revaluation** — the piece that makes the rest work. Valuations used
    to arrive one wine at a time, so a fresh cellar showed a value of nothing.

Prices are only as good as their source. Every figure carries the `source_kind`
mix it was computed from, and `estimated_share` says how much of the total rests
on model estimates rather than real prices.
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from server.db import get_pool
from server.routes.cellars import _owned_cellar
from server.valuation import (
    BEST_VALUE_CTE,
    VALUATION_ORDER,
    record_snapshot,
    store_valuations,
)
from server.wine_identity import WINE_COLUMNS, display_name, serialize_wine, to_float

router = APIRouter(tags=["value"])

# Revaluing calls a model (or a provider) per wine, so it is rate-limited and
# capped. A cellar of 500 wines is revalued over several calls, not one.
REVALUE_CONCURRENCY = 4
REVALUE_MAX_BATCH = 60
DEFAULT_STALE_DAYS = 30


class ManualValuation(BaseModel):
    """An owner-entered price. Outranks every other source for that wine."""

    account_id: str = Field(..., min_length=1, max_length=128)
    mid: float = Field(..., ge=0, le=10_000_000)
    low: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    high: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    note: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _range_ordered(self) -> "ManualValuation":
        low, high = self.low, self.high
        if low is not None and high is not None and low > high:
            raise ValueError("low must be <= high")
        if low is not None and low > self.mid:
            raise ValueError("low must be <= mid")
        if high is not None and high < self.mid:
            raise ValueError("high must be >= mid")
        return self


class RevalueRequest(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    force: bool = Field(default=False, description="Re-price even wines valued recently")
    stale_days: int = Field(default=DEFAULT_STALE_DAYS, ge=0, le=3650)
    limit: int = Field(default=REVALUE_MAX_BATCH, ge=1, le=REVALUE_MAX_BATCH)


@router.get("/cellars/{cellar_id}/value")
async def cellar_value(
    cellar_id: int,
    account_id: str = Query(..., min_length=1, max_length=128),
    movers: int = Query(default=8, ge=1, le=50),
) -> dict:
    """Total cellar value, against what was paid for it."""
    pool = get_pool()
    async with pool.acquire() as conn:
        cellar = await _owned_cellar(conn, cellar_id, account_id)

        lots = await conn.fetch(
            f"""
            WITH {BEST_VALUE_CTE}
            SELECT b.id, b.quantity, b.bin, b.purchase_price, b.currency,
                   w.id AS wine_id, w.producer, w.wine_name, w.vintage,
                   w.varietals, w.region, w.country, w.bottle_size_ml,
                   v.mid, v.low, v.high, v.value_kind, v.value_source, v.value_fetched_at
              FROM cellar_bottles b
              JOIN wines w ON w.id = b.wine_id
              LEFT JOIN best_values v ON v.wine_id = w.id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar' AND b.quantity > 0
            """,
            cellar_id,
        )

        totals = _totals(lots)
        await record_snapshot(conn, cellar_id, {**totals, "currency": "USD"})

        history = await conn.fetch(
            """
            SELECT captured_on, bottle_count, cost_basis, market_value, valued_bottles
              FROM cellar_value_snapshots
             WHERE cellar_id = $1
             ORDER BY captured_on
            """,
            cellar_id,
        )

    priced = [_lot_value(row) for row in lots if row["mid"] is not None]
    # A mover needs both a price and a cost to have moved between them.
    movable = [lot for lot in priced if lot["cost_basis"] is not None]
    movable.sort(key=lambda lot: lot["gain"], reverse=True)

    return {
        "cellar": {"id": cellar["id"], "name": cellar["name"]},
        "currency": "USD",
        **totals,
        "unrealized_gain": _round(totals["market_value"] - totals["cost_basis_priced"])
        if totals["market_value"] is not None and totals["cost_basis_priced"] is not None
        else None,
        "unrealized_gain_pct": _pct(totals["market_value"], totals["cost_basis_priced"]),
        # Strictly gained / strictly lost, so a lot can never appear in both.
        "top_gainers": [lot for lot in movable if lot["gain"] > 0][:movers],
        "top_losers": [lot for lot in reversed(movable) if lot["gain"] < 0][:movers],
        "most_valuable": sorted(priced, key=lambda lot: lot["lot_value"], reverse=True)[:movers],
        "by_region": _group(priced, lambda lot: lot["region"] or lot["country"] or "Unknown"),
        "by_varietal": _group(priced, lambda lot: lot["varietals"][0] if lot["varietals"] else "Unspecified"),
        "history": [
            {
                "date": row["captured_on"].isoformat(),
                "bottle_count": row["bottle_count"],
                "cost_basis": to_float(row["cost_basis"]),
                "market_value": to_float(row["market_value"]),
                "valued_bottles": row["valued_bottles"],
            }
            for row in history
        ],
    }


@router.post("/cellars/{cellar_id}/revalue")
async def revalue_cellar(cellar_id: int, req: RevalueRequest) -> dict:
    """Price every wine in the cellar that lacks a fresh valuation.

    This is what turns an empty "estimated value" into a real number. Without
    it, valuations only ever arrive one wine at a time from the detail sheet.
    """
    # Imported here rather than at module scope: wine_intel imports this module's
    # sibling helpers, and a top-level import would close the loop.
    from server.routes.wine_intel import fetch_valuations

    pool = get_pool()
    async with pool.acquire() as conn:
        await _owned_cellar(conn, cellar_id, req.account_id)

        freshness = "" if req.force else """
              AND NOT EXISTS (
                    SELECT 1 FROM wine_valuations v
                     WHERE v.wine_id = w.id
                       AND v.mid IS NOT NULL
                       AND v.fetched_at > NOW() - ($3 || ' days')::INTERVAL
              )
        """
        params: list = [cellar_id, req.limit]
        if not req.force:
            params.append(str(req.stale_days))

        wines = await conn.fetch(
            f"""
            SELECT DISTINCT {_prefixed(WINE_COLUMNS, 'w')}
              FROM cellar_bottles b
              JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar' AND b.quantity > 0
               {freshness}
             LIMIT $2
            """,
            *params,
        )

        remaining = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT w.id)
              FROM cellar_bottles b
              JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar' AND b.quantity > 0
            """,
            cellar_id,
        )

    if not wines:
        return {"priced": 0, "failed": 0, "attempted": 0, "wines_in_cellar": remaining,
                "message": "Every wine already has a recent valuation."}

    # Bounded concurrency: enough to be quick, not enough to hammer a provider.
    gate = asyncio.Semaphore(REVALUE_CONCURRENCY)

    async def price(wine) -> tuple[int, list[dict]]:
        async with gate:
            try:
                return wine["id"], await fetch_valuations(wine)
            except Exception:
                return wine["id"], []

    results = await asyncio.gather(*(price(w) for w in wines))

    priced = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for wine_id, rows in results:
                if rows:
                    await store_valuations(conn, wine_id, rows)
                    priced += 1

    failed = len(wines) - priced
    return {
        "priced": priced,
        "failed": failed,
        "attempted": len(wines),
        "wines_in_cellar": remaining,
        "message": (
            f"Priced {priced} of {len(wines)} wines."
            + (f" {failed} could not be priced." if failed else "")
        ),
    }


@router.put("/wines/{wine_id}/valuation")
async def set_manual_valuation(wine_id: int, payload: ManualValuation) -> dict:
    """Record what you know a bottle is worth. Outranks every other source."""
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM wines WHERE id = $1)", wine_id)
        if not exists:
            raise HTTPException(status_code=404, detail="wine not found")

        # A manual price is only meaningful for a wine the caller actually holds;
        # otherwise anyone could rewrite the shared price for every account.
        owns = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM cellar_bottles b
                  JOIN cellars c ON c.id = b.cellar_id
                 WHERE b.wine_id = $1 AND c.account_id = $2
            )
            """,
            wine_id, payload.account_id,
        )
        if not owns:
            raise HTTPException(status_code=403, detail="you do not hold this wine")

        await store_valuations(conn, wine_id, [{
            "source": "Owner",
            "source_kind": "manual",
            "low": payload.low,
            "mid": payload.mid,
            "high": payload.high,
            "currency": payload.currency.upper(),
            "note": payload.note,
            "confidence": 1.0,
        }])

        rows = await conn.fetch(
            f"""
            SELECT source, source_kind, low, mid, high, currency, note, confidence, fetched_at
              FROM wine_valuations WHERE wine_id = $1 ORDER BY {VALUATION_ORDER}
            """,
            wine_id,
        )

    return {
        "wine_id": wine_id,
        "valuations": [
            {
                "source": r["source"], "source_kind": r["source_kind"],
                "low": to_float(r["low"]), "mid": to_float(r["mid"]), "high": to_float(r["high"]),
                "currency": r["currency"], "note": r["note"],
                "estimated": r["source_kind"] == "ai_estimate",
                "fetched_at": r["fetched_at"].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/wines/{wine_id}/valuation/history")
async def wine_valuation_history(
    wine_id: int,
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    """Every price ever recorded for one wine, oldest first."""
    pool = get_pool()
    wine = await pool.fetchrow(f"SELECT {WINE_COLUMNS} FROM wines WHERE id = $1", wine_id)
    if wine is None:
        raise HTTPException(status_code=404, detail="wine not found")

    rows = await pool.fetch(
        """
        SELECT source, source_kind, low, mid, high, currency, note, recorded_at
          FROM wine_valuation_history
         WHERE wine_id = $1
         ORDER BY recorded_at DESC
         LIMIT $2
        """,
        wine_id, limit,
    )
    points = [
        {
            "source": r["source"], "source_kind": r["source_kind"],
            "low": to_float(r["low"]), "mid": to_float(r["mid"]), "high": to_float(r["high"]),
            "currency": r["currency"], "note": r["note"],
            "estimated": r["source_kind"] == "ai_estimate",
            "recorded_at": r["recorded_at"].isoformat(),
        }
        for r in reversed(rows)
    ]
    first = points[0]["mid"] if points and points[0]["mid"] is not None else None
    last = points[-1]["mid"] if points and points[-1]["mid"] is not None else None
    return {
        "wine": serialize_wine(wine),
        "points": points,
        "change": _round(last - first) if first is not None and last is not None else None,
        "change_pct": _pct(last, first),
    }


# ---------- helpers ----------


def _prefixed(columns: str, alias: str) -> str:
    return ", ".join(f"{alias}.{c.strip()}" for c in columns.split(","))


def _lot_value(row) -> dict:
    quantity = row["quantity"]
    mid = to_float(row["mid"])
    unit_cost = to_float(row["purchase_price"])
    lot_value = _round(mid * quantity)
    cost_basis = _round(unit_cost * quantity) if unit_cost is not None else None
    return {
        "bottle_id": row["id"],
        "wine_id": row["wine_id"],
        "display_name": display_name(row["producer"], row["wine_name"], row["vintage"], row["bottle_size_ml"]),
        "region": row["region"],
        "country": row["country"],
        "varietals": list(row["varietals"] or []),
        "bin": row["bin"],
        "quantity": quantity,
        "unit_value": mid,
        "unit_cost": unit_cost,
        "lot_value": lot_value,
        "cost_basis": cost_basis,
        "gain": _round(lot_value - cost_basis) if cost_basis is not None else 0.0,
        "gain_pct": _pct(lot_value, cost_basis),
        "value_kind": row["value_kind"],
        "value_source": row["value_source"],
        "estimated": row["value_kind"] == "ai_estimate",
        "valued_at": row["value_fetched_at"].isoformat() if row["value_fetched_at"] else None,
    }


def _totals(lots) -> dict:
    bottles = sum(row["quantity"] for row in lots)
    valued = [row for row in lots if row["mid"] is not None]
    valued_bottles = sum(row["quantity"] for row in valued)

    market_value = sum(to_float(row["mid"]) * row["quantity"] for row in valued) if valued else None
    market_low = sum(to_float(row["low"] or row["mid"]) * row["quantity"] for row in valued) if valued else None
    market_high = sum(to_float(row["high"] or row["mid"]) * row["quantity"] for row in valued) if valued else None

    costed = [row for row in lots if row["purchase_price"] is not None]
    cost_basis = sum(to_float(row["purchase_price"]) * row["quantity"] for row in costed) if costed else None

    # Gain is only honest where a lot has BOTH a price and a cost, so the
    # comparison uses that intersection rather than two different populations.
    both = [row for row in valued if row["purchase_price"] is not None]
    cost_basis_priced = sum(to_float(row["purchase_price"]) * row["quantity"] for row in both) if both else None
    market_value_costed = sum(to_float(row["mid"]) * row["quantity"] for row in both) if both else None

    estimated_value = sum(
        to_float(row["mid"]) * row["quantity"] for row in valued if row["value_kind"] == "ai_estimate"
    )

    return {
        "bottle_count": bottles,
        "lot_count": len(lots),
        "valued_bottles": valued_bottles,
        "valued_lots": len(valued),
        "coverage_pct": round(100 * valued_bottles / bottles, 1) if bottles else 0.0,
        "cost_basis": _round(cost_basis),
        "cost_basis_priced": _round(cost_basis_priced),
        "market_value": _round(market_value_costed if both else market_value),
        "market_value_all": _round(market_value),
        "market_low": _round(market_low),
        "market_high": _round(market_high),
        "estimated_share_pct": round(100 * estimated_value / market_value, 1)
        if market_value else 0.0,
    }


def _group(lots: list[dict], key) -> list[dict]:
    buckets: dict[str, dict] = {}
    for lot in lots:
        bucket = buckets.setdefault(key(lot), {"key": key(lot), "value": 0.0, "bottles": 0})
        bucket["value"] += lot["lot_value"]
        bucket["bottles"] += lot["quantity"]
    rows = sorted(buckets.values(), key=lambda b: b["value"], reverse=True)
    for row in rows:
        row["value"] = _round(row["value"])
    return rows[:15]


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 2)


def _pct(current: Optional[float], base: Optional[float]) -> Optional[float]:
    if current is None or not base:
        return None
    return round(100 * (current - base) / base, 1)
