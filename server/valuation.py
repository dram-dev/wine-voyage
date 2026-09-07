"""Shared valuation ranking and history recording.

Every query that asks "what is this wine worth" must agree on which of several
stored prices wins, so the ordering lives here rather than being retyped into
each router:

    manual  >  market  >  ai_estimate

A hand-entered price is the owner's own knowledge and beats a feed; a feed beats
the model's guess. Ties break on recency.
"""
from __future__ import annotations

from typing import Optional

import asyncpg

# Ordering fragment for `wine_valuations`. Used wherever a single best price is
# picked (DISTINCT ON / LATERAL / ORDER BY). Lower sorts first.
VALUATION_RANK = """
    CASE source_kind WHEN 'manual' THEN 0 WHEN 'market' THEN 1 ELSE 2 END
"""
VALUATION_ORDER = f"{VALUATION_RANK}, fetched_at DESC"

# The same ranking, for a query that has aliased the table (e.g. `v.source_kind`).
def valuation_rank(alias: str) -> str:
    return (
        f"CASE {alias}.source_kind WHEN 'manual' THEN 0 "
        f"WHEN 'market' THEN 1 ELSE 2 END"
    )


# One row per wine: the winning valuation. Callers embed this as a CTE.
BEST_VALUE_CTE = f"""
    best_values AS (
        SELECT DISTINCT ON (wine_id)
               wine_id, low, mid, high, currency,
               source AS value_source, source_kind AS value_kind, fetched_at AS value_fetched_at
          FROM wine_valuations
         WHERE mid IS NOT NULL
         ORDER BY wine_id, {VALUATION_ORDER}
    )
"""


async def store_valuations(
    conn: asyncpg.Connection | asyncpg.Pool, wine_id: int, rows: list[dict]
) -> None:
    """Upsert the current valuation AND append to the price history.

    The current-value table is what every read joins against; the history table
    is what the value tracker charts. Both are written here so a price can never
    land in one without the other.
    """
    if not rows:
        return

    payload = [
        (
            wine_id, r["source"], r["source_kind"], r.get("low"), r.get("mid"),
            r.get("high"), r.get("currency", "USD"), r.get("note"), r.get("confidence"),
        )
        for r in rows
    ]

    await conn.executemany(
        """
        INSERT INTO wine_valuations
            (wine_id, source, source_kind, low, mid, high, currency, note, confidence)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (wine_id, source) DO UPDATE SET
            source_kind = EXCLUDED.source_kind, low = EXCLUDED.low, mid = EXCLUDED.mid,
            high = EXCLUDED.high, currency = EXCLUDED.currency, note = EXCLUDED.note,
            confidence = EXCLUDED.confidence, fetched_at = NOW()
        """,
        payload,
    )
    await conn.executemany(
        """
        INSERT INTO wine_valuation_history
            (wine_id, source, source_kind, low, mid, high, currency, note)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        [row[:8] for row in payload],
    )


async def record_snapshot(
    conn: asyncpg.Connection | asyncpg.Pool, cellar_id: int, totals: dict
) -> None:
    """Write today's value point for a cellar, replacing an earlier one today.

    Called whenever the value report is computed, so simply opening the tracker
    builds the history — no cron job, no background worker.
    """
    await conn.execute(
        """
        INSERT INTO cellar_value_snapshots
            (cellar_id, captured_on, bottle_count, lot_count, cost_basis,
             market_value, valued_bottles, currency)
        VALUES ($1, CURRENT_DATE, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (cellar_id, captured_on) DO UPDATE SET
            bottle_count   = EXCLUDED.bottle_count,
            lot_count      = EXCLUDED.lot_count,
            cost_basis     = EXCLUDED.cost_basis,
            market_value   = EXCLUDED.market_value,
            valued_bottles = EXCLUDED.valued_bottles,
            currency       = EXCLUDED.currency
        """,
        cellar_id,
        totals.get("bottle_count") or 0,
        totals.get("lot_count") or 0,
        totals.get("cost_basis"),
        totals.get("market_value"),
        totals.get("valued_bottles") or 0,
        totals.get("currency") or "USD",
    )
