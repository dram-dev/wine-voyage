"""Cellars: multiple named cellars under one account, plus per-cellar stats.

An `account_id` is the stable UUID the frontend keeps in localStorage — the
same identity pattern votes.client_id uses. No passwords: holding the id is
holding the account.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.db import get_pool
from server.valuation import VALUATION_ORDER
from server.wine_identity import to_float

router = APIRouter(tags=["cellars"])

CELLAR_FIELDS = (
    "id", "account_id", "name", "location", "description",
    "capacity", "is_default", "created_at", "updated_at",
)
CELLAR_COLUMNS = ", ".join(CELLAR_FIELDS)
CELLAR_COLUMNS_C = ", ".join(f"c.{f}" for f in CELLAR_FIELDS)


class CellarIn(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    capacity: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    is_default: bool = False


class CellarPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=2000)
    capacity: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    is_default: Optional[bool] = None


@router.get("/cellars")
async def list_cellars(
    account_id: str = Query(..., min_length=1, max_length=128),
) -> list[dict]:
    """Every cellar on the account, each with a lightweight inventory rollup."""
    rows = await get_pool().fetch(
        f"""
        SELECT {CELLAR_COLUMNS_C},
               COALESCE(s.bottle_count, 0)  AS bottle_count,
               COALESCE(s.lot_count, 0)     AS lot_count,
               s.total_cost,
               s.oldest_vintage,
               s.newest_vintage
          FROM cellars c
          LEFT JOIN (
                SELECT b.cellar_id,
                       SUM(b.quantity)                        AS bottle_count,
                       COUNT(*)                               AS lot_count,
                       SUM(b.quantity * b.purchase_price)     AS total_cost,
                       MIN(w.vintage)                         AS oldest_vintage,
                       MAX(w.vintage)                         AS newest_vintage
                  FROM cellar_bottles b
                  JOIN wines w ON w.id = b.wine_id
                 WHERE b.status = 'in_cellar'
                 GROUP BY b.cellar_id
          ) s ON s.cellar_id = c.id
         WHERE c.account_id = $1
         ORDER BY c.is_default DESC, c.name
        """,
        account_id,
    )
    return [_serialize_cellar(r) for r in rows]


@router.post("/cellars", status_code=201)
async def create_cellar(cellar: CellarIn) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # First cellar on an account is the default whether or not asked for.
            has_any = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM cellars WHERE account_id = $1)", cellar.account_id
            )
            make_default = cellar.is_default or not has_any
            if make_default:
                await conn.execute(
                    "UPDATE cellars SET is_default = FALSE, updated_at = NOW() WHERE account_id = $1",
                    cellar.account_id,
                )
            try:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO cellars (account_id, name, location, description, capacity, is_default)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING {CELLAR_COLUMNS}
                    """,
                    cellar.account_id, cellar.name.strip(), cellar.location,
                    cellar.description, cellar.capacity, make_default,
                )
            except Exception as exc:
                if "cellars_account_id_name_key" in str(exc):
                    raise HTTPException(
                        status_code=409, detail=f"a cellar named {cellar.name!r} already exists"
                    )
                raise
    return _serialize_cellar(row)


@router.patch("/cellars/{cellar_id}")
async def update_cellar(
    cellar_id: int,
    patch: CellarPatch,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> dict:
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _owned_cellar(conn, cellar_id, account_id)
            if fields.get("is_default"):
                await conn.execute(
                    "UPDATE cellars SET is_default = FALSE, updated_at = NOW() "
                    "WHERE account_id = $1 AND id <> $2",
                    account_id, cellar_id,
                )
            assignments = ", ".join(f"{k} = ${i}" for i, k in enumerate(fields, start=1))
            row = await conn.fetchrow(
                f"UPDATE cellars SET {assignments}, updated_at = NOW() "
                f"WHERE id = ${len(fields) + 1} RETURNING {CELLAR_COLUMNS}",
                *fields.values(), cellar_id,
            )
    return _serialize_cellar(row)


@router.delete("/cellars/{cellar_id}", status_code=204)
async def delete_cellar(
    cellar_id: int,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> None:
    """Deletes the cellar and everything in it (bottles cascade)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await _owned_cellar(conn, cellar_id, account_id)
        await conn.execute("DELETE FROM cellars WHERE id = $1", cellar_id)


@router.get("/cellars/{cellar_id}/stats")
async def cellar_stats(
    cellar_id: int,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> dict:
    """Dashboard rollup: totals, value, and breakdowns by type/varietal/vintage/region."""
    pool = get_pool()
    async with pool.acquire() as conn:
        cellar = await _owned_cellar(conn, cellar_id, account_id)

        totals = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(b.quantity), 0)                     AS bottle_count,
                   COUNT(*)                                         AS lot_count,
                   COUNT(DISTINCT w.producer)                       AS producer_count,
                   SUM(b.quantity * b.purchase_price)               AS total_cost,
                   AVG(b.purchase_price)                            AS avg_bottle_cost,
                   MIN(w.vintage)                                   AS oldest_vintage,
                   MAX(w.vintage)                                   AS newest_vintage
              FROM cellar_bottles b
              JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
            """,
            cellar_id,
        )

        # Market value uses the best valuation we have per wine (market beats
        # estimate); wines with no valuation simply don't contribute.
        market = await conn.fetchrow(
            """
            SELECT SUM(b.quantity * v.mid)  AS market_value,
                   COUNT(DISTINCT b.wine_id)  AS valued_wines
              FROM cellar_bottles b
              JOIN LATERAL (
                    SELECT mid FROM wine_valuations
                     WHERE wine_id = b.wine_id AND mid IS NOT NULL
                     ORDER BY """ + VALUATION_ORDER + """
                     LIMIT 1
              ) v ON TRUE
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
            """,
            cellar_id,
        )

        by_type = await conn.fetch(
            """
            SELECT COALESCE(w.wine_type, 'unknown') AS key, SUM(b.quantity) AS bottles
              FROM cellar_bottles b JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
             GROUP BY 1 ORDER BY bottles DESC
            """,
            cellar_id,
        )
        by_varietal = await conn.fetch(
            """
            SELECT varietal AS key, SUM(b.quantity) AS bottles
              FROM cellar_bottles b
              JOIN wines w ON w.id = b.wine_id
              CROSS JOIN LATERAL unnest(
                    CASE WHEN cardinality(w.varietals) = 0
                         THEN ARRAY['Unspecified'] ELSE w.varietals END
              ) AS varietal
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
             GROUP BY 1 ORDER BY bottles DESC LIMIT 15
            """,
            cellar_id,
        )
        by_vintage = await conn.fetch(
            """
            SELECT w.vintage AS key, SUM(b.quantity) AS bottles
              FROM cellar_bottles b JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar' AND w.vintage IS NOT NULL
             GROUP BY 1 ORDER BY key
            """,
            cellar_id,
        )
        by_region = await conn.fetch(
            """
            SELECT COALESCE(w.region, w.country, 'Unknown') AS key, SUM(b.quantity) AS bottles
              FROM cellar_bottles b JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
             GROUP BY 1 ORDER BY bottles DESC LIMIT 15
            """,
            cellar_id,
        )
        drink_windows = await conn.fetch(
            """
            SELECT CASE
                     WHEN w.drink_from IS NULL AND w.drink_to IS NULL THEN 'unknown'
                     WHEN w.drink_from IS NOT NULL
                          AND EXTRACT(YEAR FROM NOW()) < w.drink_from  THEN 'hold'
                     WHEN w.drink_to IS NOT NULL
                          AND EXTRACT(YEAR FROM NOW()) > w.drink_to    THEN 'past'
                     WHEN w.drink_to IS NOT NULL
                          AND EXTRACT(YEAR FROM NOW()) >= w.drink_to - 1 THEN 'peak_passing'
                     ELSE 'ready'
                   END AS key,
                   SUM(b.quantity) AS bottles
              FROM cellar_bottles b JOIN wines w ON w.id = b.wine_id
             WHERE b.cellar_id = $1 AND b.status = 'in_cellar'
             GROUP BY 1
            """,
            cellar_id,
        )
        consumed = await conn.fetchrow(
            """
            SELECT COUNT(*) AS events, COALESCE(SUM(-e.quantity_delta), 0) AS bottles
              FROM bottle_events e
              JOIN cellar_bottles b ON b.id = e.bottle_id
             WHERE b.cellar_id = $1 AND e.event_type = 'consumed'
               AND e.occurred_at > NOW() - INTERVAL '365 days'
            """,
            cellar_id,
        )

    capacity = cellar["capacity"]
    bottle_count = totals["bottle_count"] or 0
    return {
        "cellar": _serialize_cellar(cellar),
        "bottle_count": bottle_count,
        "lot_count": totals["lot_count"],
        "producer_count": totals["producer_count"],
        "total_cost": to_float(totals["total_cost"]),
        "avg_bottle_cost": to_float(totals["avg_bottle_cost"]),
        "market_value": to_float(market["market_value"]),
        "valued_wines": market["valued_wines"],
        "oldest_vintage": totals["oldest_vintage"],
        "newest_vintage": totals["newest_vintage"],
        "capacity": capacity,
        "capacity_used_pct": round(100 * bottle_count / capacity, 1) if capacity else None,
        "consumed_last_year": consumed["bottles"],
        "by_type": _buckets(by_type),
        "by_varietal": _buckets(by_varietal),
        "by_vintage": _buckets(by_vintage),
        "by_region": _buckets(by_region),
        "by_drink_window": _buckets(drink_windows),
    }


async def _owned_cellar(conn, cellar_id: int, account_id: str):
    """Fetch a cellar, 404ing if it doesn't exist or belongs to another account."""
    row = await conn.fetchrow(
        f"SELECT {CELLAR_COLUMNS} FROM cellars WHERE id = $1 AND account_id = $2",
        cellar_id, account_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="cellar not found")
    return row


def _buckets(rows) -> list[dict]:
    return [{"key": r["key"], "bottles": r["bottles"]} for r in rows]


def _serialize_cellar(row) -> dict:
    data = dict(row)
    if "total_cost" in data:
        data["total_cost"] = to_float(data["total_cost"])
    return data
