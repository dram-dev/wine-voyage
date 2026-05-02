from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.db import get_pool

router = APIRouter(tags=["journal"])


class JournalEntryIn(BaseModel):
    wine_name: str = Field(min_length=1, max_length=300)
    region: Optional[str] = None
    vintage: Optional[int] = Field(default=None, ge=1900, le=2100)
    his_rating: Optional[int] = Field(default=None, ge=1, le=5)
    her_rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None


@router.get("/journal")
async def list_journal() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT id, wine_name, region, vintage, his_rating, her_rating, notes, created_at "
        "FROM journal_entries ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


@router.post("/journal", status_code=201)
async def create_journal_entry(entry: JournalEntryIn) -> dict:
    row = await get_pool().fetchrow(
        """
        INSERT INTO journal_entries (wine_name, region, vintage, his_rating, her_rating, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, wine_name, region, vintage, his_rating, her_rating, notes, created_at
        """,
        entry.wine_name, entry.region, entry.vintage,
        entry.his_rating, entry.her_rating, entry.notes,
    )
    return dict(row)


@router.delete("/journal/{entry_id}", status_code=204)
async def delete_journal_entry(entry_id: int) -> None:
    res = await get_pool().execute("DELETE FROM journal_entries WHERE id = $1", entry_id)
    if res.endswith(" 0"):
        raise HTTPException(status_code=404, detail="entry not found")
