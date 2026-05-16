"""Top-rated wineries / varietals / vintages for the world's most popular AAVs.

The flagship endpoint `/api/top-rated` returns, for the top N most popular
appellations (ranked by `appellations.popularity_rank`), the top M rated
wineries together with each winery's top-rated varietals and vintages.

Defaults match the product spec: 1000 AAVs, 40 wineries per AAV. Both are
clamped so a stray query string can't melt the database.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from server.db import get_pool

router = APIRouter(tags=["top-rated"])

MAX_AAVS = 1000
MAX_PICKS = 40


@router.get("/top-rated")
async def top_rated(
    limit: int = Query(MAX_AAVS, ge=1, le=MAX_AAVS, description="Number of popular AAVs to return"),
    per_appellation: int = Query(
        MAX_PICKS, ge=1, le=MAX_PICKS,
        description="Wineries / varietals / vintages to return per AAV",
    ),
) -> dict:
    pool = get_pool()

    appellations = await pool.fetch(
        """
        SELECT a.id, a.name, a.style, a.grapes, a.popularity_rank,
               r.id AS region_id, r.name AS region_name,
               c.id AS country_id, c.name AS country_name, c.emoji AS country_emoji
          FROM appellations a
          JOIN regions r   ON r.id = a.region_id
          JOIN countries c ON c.id = r.country_id
         WHERE a.popularity_rank IS NOT NULL
         ORDER BY a.popularity_rank ASC
         LIMIT $1
        """,
        limit,
    )
    if not appellations:
        return {"count": 0, "appellations": []}

    appellation_ids = [a["id"] for a in appellations]

    winery_rows = await pool.fetch(
        """
        SELECT id, appellation_id, name, stars, note,
               row_number() OVER (
                   PARTITION BY appellation_id
                   ORDER BY stars DESC NULLS LAST, name ASC
               ) AS rn
          FROM wineries
         WHERE appellation_id = ANY($1::text[])
        """,
        appellation_ids,
    )
    top_winery_rows = [r for r in winery_rows if r["rn"] <= per_appellation]
    winery_ids = [r["id"] for r in top_winery_rows]

    varietal_rows = []
    vintage_rows = []
    if winery_ids:
        varietal_rows = await pool.fetch(
            """
            SELECT winery_id, varietal, rating, note,
                   row_number() OVER (
                       PARTITION BY winery_id
                       ORDER BY rating DESC NULLS LAST, varietal ASC
                   ) AS rn
              FROM winery_varietals
             WHERE winery_id = ANY($1::int[])
            """,
            winery_ids,
        )
        vintage_rows = await pool.fetch(
            """
            SELECT winery_id, vintage, rating, note,
                   row_number() OVER (
                       PARTITION BY winery_id
                       ORDER BY rating DESC NULLS LAST, vintage DESC
                   ) AS rn
              FROM winery_vintages
             WHERE winery_id = ANY($1::int[])
            """,
            winery_ids,
        )

    varietals_by_winery: dict[int, list[dict]] = {}
    for r in varietal_rows:
        if r["rn"] > per_appellation:
            continue
        varietals_by_winery.setdefault(r["winery_id"], []).append({
            "varietal": r["varietal"],
            "rating": float(r["rating"]) if r["rating"] is not None else None,
            "note": r["note"],
        })

    vintages_by_winery: dict[int, list[dict]] = {}
    for r in vintage_rows:
        if r["rn"] > per_appellation:
            continue
        vintages_by_winery.setdefault(r["winery_id"], []).append({
            "vintage": r["vintage"],
            "rating": float(r["rating"]) if r["rating"] is not None else None,
            "note": r["note"],
        })

    wineries_by_appellation: dict[str, list[dict]] = {}
    for r in top_winery_rows:
        wineries_by_appellation.setdefault(r["appellation_id"], []).append({
            "id": r["id"],
            "name": r["name"],
            "stars": float(r["stars"]) if r["stars"] is not None else None,
            "note": r["note"],
            "top_varietals": varietals_by_winery.get(r["id"], []),
            "top_vintages": vintages_by_winery.get(r["id"], []),
        })

    payload = [
        {
            "id": a["id"],
            "name": a["name"],
            "style": a["style"],
            "grapes": list(a["grapes"]) if a["grapes"] else [],
            "popularity_rank": a["popularity_rank"],
            "region": {"id": a["region_id"], "name": a["region_name"]},
            "country": {
                "id": a["country_id"],
                "name": a["country_name"],
                "emoji": a["country_emoji"],
            },
            "top_wineries": wineries_by_appellation.get(a["id"], []),
        }
        for a in appellations
    ]

    return {
        "count": len(payload),
        "limit": limit,
        "per_appellation": per_appellation,
        "appellations": payload,
    }
