import hashlib
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.db import get_pool
from server.sommelier_client import cache_get, cache_set, call_sommelier

router = APIRouter(tags=["wineries"])


class MatchRequest(BaseModel):
    appellation_id: str
    taste_profile_ids: list[int]


@router.get("/wineries/{appellation_id}")
async def list_wineries(appellation_id: str) -> list[dict]:
    rows = await get_pool().fetch(
        """
        SELECT id, appellation_id, name, stars, note, source, updated_at
          FROM wineries WHERE appellation_id = $1
          ORDER BY stars DESC NULLS LAST, name
        """,
        appellation_id,
    )
    return [
        {**dict(r), "stars": float(r["stars"]) if r["stars"] is not None else None}
        for r in rows
    ]


@router.post("/wineries/match")
async def match_wineries(req: MatchRequest) -> dict:
    pool = get_pool()

    appellation = await pool.fetchrow(
        """
        SELECT a.name AS appellation_name, r.name AS region_name, c.name AS country_name,
               a.grapes, a.style
          FROM appellations a
          JOIN regions r   ON r.id = a.region_id
          JOIN countries c ON c.id = r.country_id
         WHERE a.id = $1
        """,
        req.appellation_id,
    )
    if appellation is None:
        raise HTTPException(status_code=404, detail="appellation not found")

    sorted_ids = sorted(req.taste_profile_ids)
    if not sorted_ids:
        raise HTTPException(status_code=400, detail="taste_profile_ids cannot be empty")

    profile_rows = await pool.fetch(
        "SELECT id, name, region, grape, notes FROM taste_profile WHERE id = ANY($1::int[])",
        sorted_ids,
    )
    if not profile_rows:
        raise HTTPException(status_code=404, detail="no matching taste profile entries")

    digest_input = json.dumps(
        {"a": req.appellation_id, "ids": sorted_ids}, sort_keys=True
    ).encode()
    cache_key = "wineries:match:" + hashlib.sha256(digest_input).hexdigest()

    cached = await cache_get(pool, cache_key)
    if cached is not None:
        return {"cached": True, "response": cached}

    profile_lines = "\n".join(
        f"- {p['name']}"
        + (f" ({p['region']})" if p["region"] else "")
        + (f", {p['grape']}" if p["grape"] else "")
        + (f" — {p['notes']}" if p["notes"] else "")
        for p in profile_rows
    )
    grapes = ", ".join(appellation["grapes"]) if appellation["grapes"] else "varied grapes"
    prompt = (
        "User taste profile (reference winemakers):\n"
        f"{profile_lines}\n\n"
        f"Suggest 8 producers in {appellation['appellation_name']}, "
        f"{appellation['region_name']}, {appellation['country_name']} "
        f"(style: {appellation['style'] or 'varied'}; grapes: {grapes}) "
        "working at equivalent quality and refinement to the reference winemakers. "
        'Return JSON in this exact shape: '
        '{"matches": [{"name": "...", "because": "..."}]}'
    )

    response = await call_sommelier(prompt, max_tokens=2048)
    if "error" not in response:
        await cache_set(pool, cache_key, response)
    return {"cached": False, "response": response}
