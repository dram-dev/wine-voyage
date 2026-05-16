"""Upvote / downvote endpoints for wineries, varietals, and vintages.

Each `client_id` (a stable UUID the frontend stores in localStorage) casts at
most one vote per target. Re-voting upserts (changing direction or experience
note); removing a vote is a DELETE. The optional `experience` field captures
the tasting note that motivated the vote.
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.db import get_pool

router = APIRouter(tags=["votes"])

TargetType = Literal["winery", "varietal", "vintage"]
TARGET_TABLES: dict[str, str] = {
    "winery": "wineries",
    "varietal": "winery_varietals",
    "vintage": "winery_vintages",
}
EMPTY_SUMMARY: dict[str, int] = {"up": 0, "down": 0, "score": 0}


class VoteRequest(BaseModel):
    target_type: TargetType
    target_id: int = Field(..., ge=1)
    client_id: str = Field(..., min_length=1, max_length=128)
    value: Literal[-1, 1]
    experience: Optional[str] = Field(default=None, max_length=2000)


class VoteDeleteRequest(BaseModel):
    target_type: TargetType
    target_id: int = Field(..., ge=1)
    client_id: str = Field(..., min_length=1, max_length=128)


async def _target_exists(pool, target_type: str, target_id: int) -> bool:
    # Polymorphic target_id can't carry a real FK, so we check existence
    # explicitly to return a clean 404 (otherwise we'd insert a dangling vote).
    table = TARGET_TABLES[target_type]
    return await pool.fetchval(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE id = $1)", target_id)


@router.post("/votes")
async def cast_vote(req: VoteRequest) -> dict:
    pool = get_pool()
    if not await _target_exists(pool, req.target_type, req.target_id):
        raise HTTPException(status_code=404, detail=f"{req.target_type} {req.target_id} not found")

    row = await pool.fetchrow(
        """
        INSERT INTO votes (target_type, target_id, client_id, value, experience)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (target_type, target_id, client_id) DO UPDATE
          SET value = EXCLUDED.value,
              experience = EXCLUDED.experience,
              updated_at = NOW()
        RETURNING id, value, experience, created_at, updated_at
        """,
        req.target_type, req.target_id, req.client_id, req.value, req.experience,
    )
    summary = await _summary_for_target(pool, req.target_type, [req.target_id])
    return {
        "vote": {
            **dict(row),
            "target_type": req.target_type,
            "target_id": req.target_id,
            "client_id": req.client_id,
        },
        "summary": summary.get(req.target_id, EMPTY_SUMMARY),
    }


@router.delete("/votes")
async def remove_vote(req: VoteDeleteRequest) -> dict:
    pool = get_pool()
    deleted_id = await pool.fetchval(
        """
        DELETE FROM votes
         WHERE target_type = $1 AND target_id = $2 AND client_id = $3
        RETURNING id
        """,
        req.target_type, req.target_id, req.client_id,
    )
    summary = await _summary_for_target(pool, req.target_type, [req.target_id])
    return {
        "deleted": deleted_id is not None,
        "summary": summary.get(req.target_id, EMPTY_SUMMARY),
    }


@router.get("/votes/summary")
async def votes_summary(
    target_type: TargetType,
    target_ids: str = Query(..., description="Comma-separated target ids"),
) -> dict:
    ids = _parse_id_list(target_ids)
    pool = get_pool()
    summary = await _summary_for_target(pool, target_type, ids)
    return {"target_type": target_type, "summary": summary}


@router.get("/votes/mine")
async def my_votes(
    client_id: str = Query(..., min_length=1),
    target_type: TargetType = Query(...),
    target_ids: str = Query(..., description="Comma-separated target ids"),
) -> dict:
    ids = _parse_id_list(target_ids)
    if not ids:
        return {"votes": {}}
    rows = await get_pool().fetch(
        """
        SELECT target_id, value, experience, updated_at
          FROM votes
         WHERE client_id = $1 AND target_type = $2 AND target_id = ANY($3::int[])
        """,
        client_id, target_type, ids,
    )
    return {
        "votes": {
            r["target_id"]: {
                "value": r["value"],
                "experience": r["experience"],
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        }
    }


def _parse_id_list(raw: str) -> list[int]:
    try:
        return [int(p) for p in raw.split(",") if p.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="target_ids must be comma-separated integers")


async def _summary_for_target(pool, target_type: str, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = await pool.fetch(
        """
        SELECT target_id,
               COUNT(*) FILTER (WHERE value = 1)  AS up,
               COUNT(*) FILTER (WHERE value = -1) AS down,
               COALESCE(SUM(value), 0)            AS score
          FROM votes
         WHERE target_type = $1 AND target_id = ANY($2::int[])
         GROUP BY target_id
        """,
        target_type, ids,
    )
    return {r["target_id"]: {"up": r["up"], "down": r["down"], "score": r["score"]} for r in rows}


async def _mine_for_target(pool, target_type: str, ids: list[int], client_id: str) -> dict[int, int]:
    if not ids:
        return {}
    rows = await pool.fetch(
        """
        SELECT target_id, value FROM votes
         WHERE client_id = $1 AND target_type = $2 AND target_id = ANY($3::int[])
        """,
        client_id, target_type, ids,
    )
    return {r["target_id"]: r["value"] for r in rows}


async def load_votes_for_targets(
    pool,
    *,
    winery_ids: list[int] | None = None,
    varietal_ids: list[int] | None = None,
    vintage_ids: list[int] | None = None,
    client_id: str | None = None,
) -> dict:
    """Aggregate helper used by other routers to enrich responses with vote data.

    Returns:
        {
            "summary": {"winery": {id: {up, down, score}}, "varietal": {...}, "vintage": {...}},
            "mine":    {"winery": {id: value}, ...}  # only populated when client_id is provided
        }
    """
    pairs = (
        ("winery", winery_ids or []),
        ("varietal", varietal_ids or []),
        ("vintage", vintage_ids or []),
    )
    tasks = [_summary_for_target(pool, t, ids) for t, ids in pairs]
    if client_id:
        tasks.extend(_mine_for_target(pool, t, ids, client_id) for t, ids in pairs)
    results = await asyncio.gather(*tasks)

    return {
        "summary": {t: results[i] for i, (t, _) in enumerate(pairs)},
        "mine": {
            t: (results[3 + i] if client_id else {})
            for i, (t, _) in enumerate(pairs)
        },
    }
