from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.db import get_pool

router = APIRouter(tags=["trips"])


class TripIn(BaseModel):
    appellation_id: str


class TripPatch(BaseModel):
    visited: Optional[bool] = None


@router.get("/trips")
async def list_trips() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, appellation_id, visited, created_at FROM trips ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("/trips", status_code=201)
async def create_trip(trip: TripIn) -> dict:
    row = await get_pool().fetchrow(
        """
        INSERT INTO trips (appellation_id) VALUES ($1)
        RETURNING id, appellation_id, visited, created_at
        """,
        trip.appellation_id,
    )
    return dict(row)


@router.patch("/trips/{trip_id}")
async def update_trip(trip_id: int, patch: TripPatch) -> dict:
    pool = get_pool()
    if patch.visited is None:
        # toggle if no explicit value
        row = await pool.fetchrow(
            "UPDATE trips SET visited = NOT visited WHERE id = $1 "
            "RETURNING id, appellation_id, visited, created_at",
            trip_id,
        )
    else:
        row = await pool.fetchrow(
            "UPDATE trips SET visited = $2 WHERE id = $1 "
            "RETURNING id, appellation_id, visited, created_at",
            trip_id, patch.visited,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="trip not found")
    return dict(row)


@router.delete("/trips/{trip_id}", status_code=204)
async def delete_trip(trip_id: int) -> None:
    res = await get_pool().execute("DELETE FROM trips WHERE id = $1", trip_id)
    if res.endswith(" 0"):
        raise HTTPException(status_code=404, detail="trip not found")
