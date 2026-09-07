"""Bottle inventory: add, search, sort, drink, move.

A "bottle" row is really a *lot* — N identical bottles of one wine sitting in
one bin of one cellar. Drinking one decrements the lot and appends a
`bottle_events` row, so the cellar can answer both "what do I have" and "what
did we drink last year".

Search is the workhorse: free text across producer/cuvée/region/varietal, plus
structured filters (vintage range, varietal, country, region, producer, type,
drink window, score, price) and a sort whitelist.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from server.db import get_pool
from server.routes.cellars import _owned_cellar
from server.wine_identity import WINE_COLUMNS, serialize_wine, to_float, upsert_wine

router = APIRouter(tags=["bottles"])

WineType = Literal["red", "white", "rose", "sparkling", "dessert", "fortified", "other"]
BottleStatus = Literal["in_cellar", "consumed", "gifted", "sold", "lost"]
DrinkWindow = Literal["unknown", "hold", "ready", "peak_passing", "past"]

# Sort keys the API accepts, mapped to SQL. Whitelisted rather than
# interpolated so `sort` can never reach the query as raw SQL.
SORT_EXPRESSIONS: dict[str, str] = {
    "added": "b.created_at",
    "vintage": "w.vintage",
    "producer": "lower(w.producer)",
    "name": "lower(w.producer), lower(coalesce(w.wine_name, ''))",
    "varietal": "lower(coalesce(w.varietals[1], ''))",
    "region": "lower(coalesce(w.region, w.country, ''))",
    "country": "lower(coalesce(w.country, ''))",
    "quantity": "b.quantity",
    "price": "b.purchase_price",
    "value": "val.mid",
    "score": "sc.best_score",
    "my_rating": "b.my_rating",
    "drink_from": "w.drink_from",
    "bin": "lower(coalesce(b.bin, ''))",
}
DEFAULT_SORT = "added"

# Ranked score per wine: a real critic beats the community, which beats an
# AI estimate. One row per wine, joined into search results and detail.
BEST_SCORE_CTE = """
    best_scores AS (
        SELECT DISTINCT ON (wine_id)
               wine_id,
               score AS best_score,
               source AS best_score_source,
               source_kind AS best_score_kind
          FROM wine_scores
         WHERE score IS NOT NULL AND scale = '100'
         ORDER BY wine_id,
                  CASE source_kind WHEN 'critic' THEN 0 WHEN 'community' THEN 1 ELSE 2 END,
                  fetched_at DESC
    )
"""
BEST_VALUE_CTE = """
    best_values AS (
        SELECT DISTINCT ON (wine_id)
               wine_id, low, mid, high, currency, source AS value_source, source_kind AS value_kind
          FROM wine_valuations
         WHERE mid IS NOT NULL
         ORDER BY wine_id, (source_kind = 'market') DESC, fetched_at DESC
    )
"""


class WineIn(BaseModel):
    producer: str = Field(..., min_length=1, max_length=300)
    wine_name: Optional[str] = Field(default=None, max_length=300)
    vintage: Optional[int] = Field(default=None, ge=1800, le=2100)
    varietals: list[str] = Field(default_factory=list, max_length=12)
    wine_type: Optional[WineType] = None
    country: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=200)
    appellation: Optional[str] = Field(default=None, max_length=200)
    appellation_id: Optional[str] = Field(default=None, max_length=200)
    bottle_size_ml: int = Field(default=750, ge=50, le=30000)
    abv: Optional[float] = Field(default=None, ge=0, le=100)
    drink_from: Optional[int] = Field(default=None, ge=1800, le=2200)
    drink_to: Optional[int] = Field(default=None, ge=1800, le=2200)
    label_image_url: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _drink_window_ordered(self) -> "WineIn":
        if self.drink_from and self.drink_to and self.drink_from > self.drink_to:
            raise ValueError("drink_from must be <= drink_to")
        return self


class BottleIn(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    cellar_id: int = Field(..., ge=1)
    wine: WineIn
    quantity: int = Field(default=1, ge=1, le=10000)
    bin: Optional[str] = Field(default=None, max_length=100)
    purchase_price: Optional[float] = Field(default=None, ge=0)
    purchase_date: Optional[date] = None
    purchase_source: Optional[str] = Field(default=None, max_length=300)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    my_rating: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=4000)


class BottlePatch(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=0, le=10000)
    bin: Optional[str] = Field(default=None, max_length=100)
    purchase_price: Optional[float] = Field(default=None, ge=0)
    purchase_date: Optional[date] = None
    purchase_source: Optional[str] = Field(default=None, max_length=300)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    my_rating: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[BottleStatus] = None


class ConsumeIn(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    quantity: int = Field(default=1, ge=1, le=10000)
    disposition: Literal["consumed", "gifted", "sold", "lost"] = "consumed"
    my_rating: Optional[float] = Field(default=None, ge=0, le=100)
    note: Optional[str] = Field(default=None, max_length=4000)


class MoveIn(BaseModel):
    account_id: str = Field(..., min_length=1, max_length=128)
    to_cellar_id: int = Field(..., ge=1)
    quantity: Optional[int] = Field(default=None, ge=1, le=10000)
    bin: Optional[str] = Field(default=None, max_length=100)


@router.get("/bottles")
async def search_bottles(
    account_id: str = Query(..., min_length=1, max_length=128),
    cellar_id: Optional[int] = Query(default=None, ge=1, description="Omit to search every cellar"),
    q: Optional[str] = Query(default=None, max_length=200, description="Free text over producer, cuvée, region, varietal, bin"),
    vintage_min: Optional[int] = Query(default=None, ge=1800, le=2100),
    vintage_max: Optional[int] = Query(default=None, ge=1800, le=2100),
    varietal: Optional[str] = Query(default=None, max_length=100),
    country: Optional[str] = Query(default=None, max_length=120),
    region: Optional[str] = Query(default=None, max_length=200),
    producer: Optional[str] = Query(default=None, max_length=300),
    wine_type: Optional[WineType] = None,
    drink_window: Optional[DrinkWindow] = None,
    status: BottleStatus = Query(default="in_cellar"),
    bin: Optional[str] = Query(default=None, max_length=100),
    min_score: Optional[float] = Query(default=None, ge=0, le=100),
    min_price: Optional[float] = Query(default=None, ge=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    include_empty: bool = Query(default=False, description="Include lots whose quantity has hit 0"),
    sort: str = Query(default=DEFAULT_SORT),
    order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if sort not in SORT_EXPRESSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"sort must be one of: {', '.join(sorted(SORT_EXPRESSIONS))}",
        )
    if vintage_min and vintage_max and vintage_min > vintage_max:
        raise HTTPException(status_code=400, detail="vintage_min must be <= vintage_max")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=400, detail="min_price must be <= max_price")

    where, params = _build_filters(
        account_id=account_id, cellar_id=cellar_id, q=q,
        vintage_min=vintage_min, vintage_max=vintage_max, varietal=varietal,
        country=country, region=region, producer=producer, wine_type=wine_type,
        drink_window=drink_window, status=status, bin=bin, min_score=min_score,
        min_price=min_price, max_price=max_price, include_empty=include_empty,
    )

    # NULLs last in both directions: an unpriced bottle shouldn't lead the
    # "cheapest first" list any more than the "most expensive first" one.
    direction = "ASC" if order == "asc" else "DESC"
    order_by = ", ".join(
        f"{expr} {direction} NULLS LAST" for expr in SORT_EXPRESSIONS[sort].split(", ")
    )

    pool = get_pool()
    rows = await pool.fetch(
        f"""
        WITH {BEST_SCORE_CTE}, {BEST_VALUE_CTE}
        SELECT b.id, b.cellar_id, b.quantity, b.bin, b.purchase_price, b.purchase_date,
               b.purchase_source, b.currency, b.my_rating, b.notes, b.status,
               b.created_at, b.updated_at,
               c.name AS cellar_name,
               {_wine_select()},
               sc.best_score, sc.best_score_source, sc.best_score_kind,
               val.low AS value_low, val.mid AS value_mid, val.high AS value_high,
               val.currency AS value_currency, val.value_source, val.value_kind,
               COUNT(*) OVER () AS total_count
          FROM cellar_bottles b
          JOIN cellars c ON c.id = b.cellar_id
          JOIN wines   w ON w.id = b.wine_id
          LEFT JOIN best_scores sc ON sc.wine_id = w.id
          LEFT JOIN best_values val ON val.wine_id = w.id
         WHERE {where}
         ORDER BY {order_by}, b.id DESC
         LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """,
        *params, limit, offset,
    )

    total = rows[0]["total_count"] if rows else 0
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "order": order,
        "bottles": [_serialize_bottle(r) for r in rows],
    }


@router.get("/bottles/facets")
async def bottle_facets(
    account_id: str = Query(..., min_length=1, max_length=128),
    cellar_id: Optional[int] = Query(default=None, ge=1),
    status: BottleStatus = Query(default="in_cellar"),
) -> dict:
    """Distinct filter values with counts, so the UI can build its filter menus
    from what is actually in the cellar rather than a hardcoded list."""
    where, params = _build_filters(account_id=account_id, cellar_id=cellar_id, status=status)
    pool = get_pool()

    joined = """
        FROM cellar_bottles b
        JOIN cellars c ON c.id = b.cellar_id
        JOIN wines   w ON w.id = b.wine_id
    """
    # Every facet is the same shape: one key column, bottles summed, ordered by
    # popularity. Only the key expression and the extra predicate differ.
    facet_specs: list[tuple[str, str, str, str]] = [
        ("countries", "w.country", "AND w.country IS NOT NULL", "bottles DESC, key"),
        ("regions", "w.region", "AND w.region IS NOT NULL", "bottles DESC, key"),
        ("producers", "w.producer", "", "bottles DESC, key"),
        ("wine_types", "w.wine_type", "AND w.wine_type IS NOT NULL", "bottles DESC, key"),
        ("vintages", "w.vintage", "AND w.vintage IS NOT NULL", "key DESC"),
        ("bins", "b.bin", "AND b.bin IS NOT NULL", "key"),
    ]
    queries = [
        pool.fetch(
            f"SELECT {key} AS key, SUM(b.quantity) AS bottles {joined} "
            f"WHERE {where} {extra} GROUP BY 1 ORDER BY {ordering}",
            *params,
        )
        for _, key, extra, ordering in facet_specs
    ]
    # Varietals live in an array column, so this one needs its own unnest join.
    queries.append(
        pool.fetch(
            f"""
            SELECT varietal AS key, SUM(b.quantity) AS bottles
            {joined}
              CROSS JOIN LATERAL unnest(w.varietals) AS varietal
             WHERE {where}
             GROUP BY 1 ORDER BY bottles DESC, key
            """,
            *params,
        )
    )
    results = await asyncio.gather(*queries)

    facets = {
        name: [{"key": r["key"], "bottles": r["bottles"]} for r in rows]
        for (name, _, _, _), rows in zip(facet_specs, results)
    }
    facets["varietals"] = [{"key": r["key"], "bottles": r["bottles"]} for r in results[-1]]
    facets["sorts"] = sorted(SORT_EXPRESSIONS)
    facets["drink_windows"] = sorted(_DRINK_WINDOW_CLAUSES)
    return facets


@router.post("/bottles", status_code=201)
async def add_bottle(payload: BottleIn) -> dict:
    """Add bottles to a cellar, deduping onto an existing lot when the same wine
    is already in the same bin."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _owned_cellar(conn, payload.cellar_id, payload.account_id)
            wine = await upsert_wine(conn, payload.wine.model_dump())
            bottle = await conn.fetchrow(
                """
                INSERT INTO cellar_bottles (
                    cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                    purchase_source, currency, my_rating, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (cellar_id, wine_id, bin) DO UPDATE SET
                    quantity        = cellar_bottles.quantity + EXCLUDED.quantity,
                    purchase_price  = COALESCE(EXCLUDED.purchase_price, cellar_bottles.purchase_price),
                    purchase_date   = COALESCE(EXCLUDED.purchase_date, cellar_bottles.purchase_date),
                    purchase_source = COALESCE(EXCLUDED.purchase_source, cellar_bottles.purchase_source),
                    my_rating       = COALESCE(EXCLUDED.my_rating, cellar_bottles.my_rating),
                    notes           = COALESCE(EXCLUDED.notes, cellar_bottles.notes),
                    status          = 'in_cellar',
                    updated_at      = NOW()
                RETURNING id, cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                          purchase_source, currency, my_rating, notes, status, created_at, updated_at
                """,
                payload.cellar_id, wine["id"], payload.quantity, payload.bin,
                payload.purchase_price, payload.purchase_date, payload.purchase_source,
                payload.currency.upper(), payload.my_rating, payload.notes,
            )
            await _log_event(conn, bottle["id"], "added", payload.quantity, payload.purchase_source)

    return {**_serialize_bottle(bottle), "wine": serialize_wine(wine)}


@router.get("/bottles/{bottle_id}")
async def get_bottle(
    bottle_id: int,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> dict:
    pool = get_pool()
    row = await pool.fetchrow(
        f"""
        WITH {BEST_SCORE_CTE}, {BEST_VALUE_CTE}
        SELECT b.id, b.cellar_id, b.quantity, b.bin, b.purchase_price, b.purchase_date,
               b.purchase_source, b.currency, b.my_rating, b.notes, b.status,
               b.created_at, b.updated_at,
               c.name AS cellar_name,
               {_wine_select()},
               sc.best_score, sc.best_score_source, sc.best_score_kind,
               val.low AS value_low, val.mid AS value_mid, val.high AS value_high,
               val.currency AS value_currency, val.value_source, val.value_kind
          FROM cellar_bottles b
          JOIN cellars c ON c.id = b.cellar_id
          JOIN wines   w ON w.id = b.wine_id
          LEFT JOIN best_scores sc ON sc.wine_id = w.id
          LEFT JOIN best_values val ON val.wine_id = w.id
         WHERE b.id = $1 AND c.account_id = $2
        """,
        bottle_id, account_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="bottle not found")

    events = await pool.fetch(
        "SELECT event_type, quantity_delta, note, occurred_at FROM bottle_events "
        "WHERE bottle_id = $1 ORDER BY occurred_at DESC LIMIT 50",
        bottle_id,
    )
    return {
        **_serialize_bottle(row),
        "history": [
            {
                "event_type": e["event_type"],
                "quantity_delta": e["quantity_delta"],
                "note": e["note"],
                "occurred_at": e["occurred_at"].isoformat(),
            }
            for e in events
        ],
    }


@router.patch("/bottles/{bottle_id}")
async def update_bottle(
    bottle_id: int,
    patch: BottlePatch,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> dict:
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    if "currency" in fields and fields["currency"]:
        fields["currency"] = fields["currency"].upper()

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _owned_bottle(conn, bottle_id, account_id)
            assignments = ", ".join(f"{k} = ${i}" for i, k in enumerate(fields, start=1))
            row = await conn.fetchrow(
                f"""
                UPDATE cellar_bottles SET {assignments}, updated_at = NOW()
                 WHERE id = ${len(fields) + 1}
                RETURNING id, cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                          purchase_source, currency, my_rating, notes, status, created_at, updated_at
                """,
                *fields.values(), bottle_id,
            )
            if "quantity" in fields and fields["quantity"] != before["quantity"]:
                await _log_event(
                    conn, bottle_id, "adjusted", fields["quantity"] - before["quantity"], "manual edit"
                )
    return _serialize_bottle(row)


@router.post("/bottles/{bottle_id}/consume")
async def consume_bottle(bottle_id: int, payload: ConsumeIn) -> dict:
    """Drink (or gift/sell/lose) bottles from a lot, recording the event."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            bottle = await _owned_bottle(conn, bottle_id, payload.account_id)
            if bottle["quantity"] < payload.quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"only {bottle['quantity']} bottle(s) in this lot",
                )
            remaining = bottle["quantity"] - payload.quantity
            row = await conn.fetchrow(
                """
                UPDATE cellar_bottles
                   SET quantity   = $2,
                       my_rating  = COALESCE($3, my_rating),
                       status     = CASE WHEN $2 = 0 THEN $4 ELSE status END,
                       updated_at = NOW()
                 WHERE id = $1
                RETURNING id, cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                          purchase_source, currency, my_rating, notes, status, created_at, updated_at
                """,
                bottle_id, remaining, payload.my_rating, payload.disposition,
            )
            await _log_event(conn, bottle_id, payload.disposition, -payload.quantity, payload.note)
    return {**_serialize_bottle(row), "remaining": remaining}


@router.post("/bottles/{bottle_id}/move")
async def move_bottle(bottle_id: int, payload: MoveIn) -> dict:
    """Move all or part of a lot into another cellar on the same account."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            bottle = await _owned_bottle(conn, bottle_id, payload.account_id)
            await _owned_cellar(conn, payload.to_cellar_id, payload.account_id)
            if payload.to_cellar_id == bottle["cellar_id"] and payload.bin == bottle["bin"]:
                raise HTTPException(status_code=400, detail="bottle is already there")

            moving = payload.quantity or bottle["quantity"]
            if moving > bottle["quantity"]:
                raise HTTPException(
                    status_code=409, detail=f"only {bottle['quantity']} bottle(s) in this lot"
                )

            destination = await conn.fetchrow(
                """
                INSERT INTO cellar_bottles (
                    cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                    purchase_source, currency, my_rating, notes
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (cellar_id, wine_id, bin) DO UPDATE SET
                    quantity   = cellar_bottles.quantity + EXCLUDED.quantity,
                    status     = 'in_cellar',
                    updated_at = NOW()
                RETURNING id, cellar_id, wine_id, quantity, bin, purchase_price, purchase_date,
                          purchase_source, currency, my_rating, notes, status, created_at, updated_at
                """,
                payload.to_cellar_id, bottle["wine_id"], moving, payload.bin,
                bottle["purchase_price"], bottle["purchase_date"], bottle["purchase_source"],
                bottle["currency"], bottle["my_rating"], bottle["notes"],
            )

            remaining = bottle["quantity"] - moving
            if remaining:
                await conn.execute(
                    "UPDATE cellar_bottles SET quantity = $2, updated_at = NOW() WHERE id = $1",
                    bottle_id, remaining,
                )
            else:
                await conn.execute("DELETE FROM cellar_bottles WHERE id = $1", bottle_id)

            await _log_event(
                conn, destination["id"], "moved", moving,
                f"moved from cellar {bottle['cellar_id']}",
            )
    return {"moved": moving, "remaining": remaining, "bottle": _serialize_bottle(destination)}


@router.delete("/bottles/{bottle_id}", status_code=204)
async def delete_bottle(
    bottle_id: int,
    account_id: str = Query(..., min_length=1, max_length=128),
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await _owned_bottle(conn, bottle_id, account_id)
        await conn.execute("DELETE FROM cellar_bottles WHERE id = $1", bottle_id)


def _wine_select() -> str:
    """Alias every wine column as w_* so it can't collide with the bottle's."""
    return ", ".join(f"w.{col.strip()} AS w_{col.strip()}" for col in WINE_COLUMNS.split(","))


def _build_filters(**kw) -> tuple[str, list]:
    """Assemble the shared WHERE clause for search and facets.

    Every value goes in as a positional parameter — nothing user-supplied is
    ever interpolated into the SQL text.
    """
    clauses = ["c.account_id = $1"]
    params: list = [kw["account_id"]]

    def add(clause_template: str, value) -> None:
        params.append(value)
        clauses.append(clause_template.format(n=len(params)))

    if kw.get("cellar_id"):
        add("b.cellar_id = ${n}", kw["cellar_id"])
    if kw.get("status"):
        add("b.status = ${n}", kw["status"])
    if not kw.get("include_empty", False):
        clauses.append("b.quantity > 0")
    if kw.get("q"):
        add(
            "(w.producer ILIKE '%' || ${n} || '%' OR w.wine_name ILIKE '%' || ${n} || '%' "
            "OR w.region ILIKE '%' || ${n} || '%' OR w.appellation ILIKE '%' || ${n} || '%' "
            "OR w.country ILIKE '%' || ${n} || '%' OR b.bin ILIKE '%' || ${n} || '%' "
            "OR EXISTS (SELECT 1 FROM unnest(w.varietals) v WHERE v ILIKE '%' || ${n} || '%'))",
            kw["q"].strip(),
        )
    if kw.get("vintage_min"):
        add("w.vintage >= ${n}", kw["vintage_min"])
    if kw.get("vintage_max"):
        add("w.vintage <= ${n}", kw["vintage_max"])
    if kw.get("varietal"):
        add("EXISTS (SELECT 1 FROM unnest(w.varietals) v WHERE lower(v) = lower(${n}))", kw["varietal"])
    if kw.get("country"):
        add("lower(w.country) = lower(${n})", kw["country"])
    if kw.get("region"):
        add("lower(w.region) = lower(${n})", kw["region"])
    if kw.get("producer"):
        add("w.producer ILIKE '%' || ${n} || '%'", kw["producer"])
    if kw.get("wine_type"):
        add("w.wine_type = ${n}", kw["wine_type"])
    if kw.get("bin"):
        add("b.bin = ${n}", kw["bin"])
    if kw.get("min_price") is not None:
        add("b.purchase_price >= ${n}", kw["min_price"])
    if kw.get("max_price") is not None:
        add("b.purchase_price <= ${n}", kw["max_price"])
    if kw.get("min_score") is not None:
        add(
            "EXISTS (SELECT 1 FROM wine_scores s WHERE s.wine_id = w.id "
            "AND s.scale = '100' AND s.score >= ${n})",
            kw["min_score"],
        )
    if kw.get("drink_window"):
        clauses.append(_DRINK_WINDOW_CLAUSES[kw["drink_window"]])

    return " AND ".join(clauses), params


# Mirrors wine_identity.drink_window_status, evaluated in SQL so the filter can
# run in the database instead of over a fetched page.
_DRINK_WINDOW_CLAUSES: dict[str, str] = {
    "unknown": "(w.drink_from IS NULL AND w.drink_to IS NULL)",
    "hold": "(w.drink_from IS NOT NULL AND EXTRACT(YEAR FROM NOW()) < w.drink_from)",
    "past": "(w.drink_to IS NOT NULL AND EXTRACT(YEAR FROM NOW()) > w.drink_to)",
    "peak_passing": (
        "(w.drink_to IS NOT NULL AND EXTRACT(YEAR FROM NOW()) BETWEEN w.drink_to - 1 AND w.drink_to "
        "AND (w.drink_from IS NULL OR EXTRACT(YEAR FROM NOW()) >= w.drink_from))"
    ),
    "ready": (
        "((w.drink_from IS NOT NULL OR w.drink_to IS NOT NULL) "
        "AND (w.drink_from IS NULL OR EXTRACT(YEAR FROM NOW()) >= w.drink_from) "
        "AND (w.drink_to IS NULL OR EXTRACT(YEAR FROM NOW()) < w.drink_to - 1))"
    ),
}


async def _owned_bottle(conn, bottle_id: int, account_id: str):
    row = await conn.fetchrow(
        """
        SELECT b.id, b.cellar_id, b.wine_id, b.quantity, b.bin, b.purchase_price,
               b.purchase_date, b.purchase_source, b.currency, b.my_rating, b.notes, b.status
          FROM cellar_bottles b
          JOIN cellars c ON c.id = b.cellar_id
         WHERE b.id = $1 AND c.account_id = $2
         FOR UPDATE OF b
        """,
        bottle_id, account_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="bottle not found")
    return row


async def _log_event(conn, bottle_id: int, event_type: str, delta: int, note: Optional[str]) -> None:
    await conn.execute(
        "INSERT INTO bottle_events (bottle_id, event_type, quantity_delta, note) VALUES ($1, $2, $3, $4)",
        bottle_id, event_type, delta, note,
    )


def _serialize_bottle(row) -> dict:
    data = dict(row)
    bottle = {
        "id": data["id"],
        "cellar_id": data["cellar_id"],
        "cellar_name": data.get("cellar_name"),
        "quantity": data["quantity"],
        "bin": data["bin"],
        "purchase_price": to_float(data["purchase_price"]),
        "purchase_date": data["purchase_date"].isoformat() if data.get("purchase_date") else None,
        "purchase_source": data["purchase_source"],
        "currency": data["currency"],
        "my_rating": to_float(data["my_rating"]),
        "notes": data["notes"],
        "status": data["status"],
        "created_at": data["created_at"].isoformat() if data.get("created_at") else None,
        "updated_at": data["updated_at"].isoformat() if data.get("updated_at") else None,
    }
    if "w_id" in data:
        bottle["wine"] = serialize_wine(row, prefix="w_")
        bottle["best_score"] = (
            {
                "score": to_float(data["best_score"]),
                "source": data["best_score_source"],
                "source_kind": data["best_score_kind"],
            }
            if data.get("best_score") is not None
            else None
        )
        bottle["value"] = (
            {
                "low": to_float(data["value_low"]),
                "mid": to_float(data["value_mid"]),
                "high": to_float(data["value_high"]),
                "currency": data["value_currency"],
                "source": data["value_source"],
                "source_kind": data["value_kind"],
                "estimated": data["value_kind"] == "ai_estimate",
            }
            if data.get("value_mid") is not None
            else None
        )
        if bottle["value"] and bottle["quantity"]:
            bottle["lot_value"] = round(bottle["value"]["mid"] * bottle["quantity"], 2)
    else:
        bottle["wine_id"] = data.get("wine_id")
    return bottle
