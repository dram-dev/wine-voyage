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
from server.routes.votes import load_votes_for_targets

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
    client_id: str | None = Query(default=None, description="Optional client UUID for my_vote enrichment"),
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
            SELECT id, winery_id, varietal, rating, note,
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
            SELECT id, winery_id, vintage, rating, note,
                   row_number() OVER (
                       PARTITION BY winery_id
                       ORDER BY rating DESC NULLS LAST, vintage DESC
                   ) AS rn
              FROM winery_vintages
             WHERE winery_id = ANY($1::int[])
            """,
            winery_ids,
        )

    top_varietal_rows = [r for r in varietal_rows if r["rn"] <= per_appellation]
    top_vintage_rows = [r for r in vintage_rows if r["rn"] <= per_appellation]
    varietal_ids = [r["id"] for r in top_varietal_rows]
    vintage_ids = [r["id"] for r in top_vintage_rows]

    vote_data = await load_votes_for_targets(
        pool,
        winery_ids=winery_ids,
        varietal_ids=varietal_ids,
        vintage_ids=vintage_ids,
        client_id=client_id,
    )
    empty_summary = {"up": 0, "down": 0, "score": 0}

    varietals_by_winery: dict[int, list[dict]] = {}
    for r in top_varietal_rows:
        varietals_by_winery.setdefault(r["winery_id"], []).append({
            "id": r["id"],
            "varietal": r["varietal"],
            "rating": float(r["rating"]) if r["rating"] is not None else None,
            "note": r["note"],
            "votes": vote_data["summary"]["varietal"].get(r["id"], empty_summary),
            "my_vote": vote_data["mine"]["varietal"].get(r["id"]) if client_id else None,
        })

    vintages_by_winery: dict[int, list[dict]] = {}
    for r in top_vintage_rows:
        vintages_by_winery.setdefault(r["winery_id"], []).append({
            "id": r["id"],
            "vintage": r["vintage"],
            "rating": float(r["rating"]) if r["rating"] is not None else None,
            "note": r["note"],
            "votes": vote_data["summary"]["vintage"].get(r["id"], empty_summary),
            "my_vote": vote_data["mine"]["vintage"].get(r["id"]) if client_id else None,
        })

    wineries_by_appellation: dict[str, list[dict]] = {}
    for r in top_winery_rows:
        wineries_by_appellation.setdefault(r["appellation_id"], []).append({
            "id": r["id"],
            "name": r["name"],
            "stars": float(r["stars"]) if r["stars"] is not None else None,
            "note": r["note"],
            "votes": vote_data["summary"]["winery"].get(r["id"], empty_summary),
            "my_vote": vote_data["mine"]["winery"].get(r["id"]) if client_id else None,
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
