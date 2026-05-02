from fastapi import APIRouter, HTTPException

from server.db import get_pool

router = APIRouter(tags=["appellations"])

_BASE_QUERY = """
SELECT a.id, a.name, a.grapes, a.style, a.lat, a.lng,
       r.id  AS region_id,  r.name AS region_name,
       c.id  AS country_id, c.name AS country_name, c.emoji, c.color
  FROM appellations a
  JOIN regions   r ON r.id = a.region_id
  JOIN countries c ON c.id = r.country_id
"""


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "grapes": list(row["grapes"]) if row["grapes"] else [],
        "style": row["style"],
        "lat": float(row["lat"]) if row["lat"] is not None else None,
        "lng": float(row["lng"]) if row["lng"] is not None else None,
        "region": {"id": row["region_id"], "name": row["region_name"]},
        "country": {
            "id": row["country_id"],
            "name": row["country_name"],
            "emoji": row["emoji"],
            "color": row["color"],
        },
    }


@router.get("/appellations")
async def list_appellations() -> list[dict]:
    rows = await get_pool().fetch(_BASE_QUERY + " ORDER BY c.name, r.name, a.name")
    return [_row_to_dict(r) for r in rows]


@router.get("/appellations/{appellation_id}")
async def get_appellation(appellation_id: str) -> dict:
    row = await get_pool().fetchrow(_BASE_QUERY + " WHERE a.id = $1", appellation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="appellation not found")
    return _row_to_dict(row)
