from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.db import get_pool

router = APIRouter(tags=["taste"])


class TasteEntryIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    region: Optional[str] = None
    grape: Optional[str] = None
    notes: Optional[str] = None


@router.get("/taste")
async def list_taste() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, name, region, grape, notes, created_at FROM taste_profile "
        "ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("/taste", status_code=201)
async def create_taste(entry: TasteEntryIn) -> dict:
    row = await get_pool().fetchrow(
        """
        INSERT INTO taste_profile (name, region, grape, notes)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, region, grape, notes, created_at
        """,
        entry.name, entry.region, entry.grape, entry.notes,
    )
    return dict(row)


@router.delete("/taste/{entry_id}", status_code=204)
async def delete_taste(entry_id: int) -> None:
    res = await get_pool().execute("DELETE FROM taste_profile WHERE id = $1", entry_id)
    if res.endswith(" 0"):
        raise HTTPException(status_code=404, detail="entry not found")
