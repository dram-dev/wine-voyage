"""Seed the popularity ranking + top 40 wineries / varietals / vintages per AAV.

Reads `data/popular_aavs.json` (array of appellation ids in popularity order)
and, for every AAV, asks Claude for the 40 highest-rated wineries together with
their top varietals and top vintages. Costs roughly $0.01-0.02 per AAV depending
on the model — a full 1000-AAV pass takes a few hours and a few dollars.

    python -m scripts.seed_top_rated --dry-run        # preview only
    python -m scripts.seed_top_rated --limit 25       # first 25 AAVs only
    python -m scripts.seed_top_rated                  # full pass

The script is idempotent: re-running upserts the popularity rank, removes any
prior AI-sourced rows for each AAV, and inserts the freshly generated set.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from server.config import settings
from server.sommelier_client import call_sommelier

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "popular_aavs.json"
RATE_LIMIT_SECONDS = 1.0
PICKS_PER_AAV = 40


def build_prompt(name: str, region: str, country: str, style: str | None, grapes: list[str]) -> str:
    grape_str = ", ".join(grapes) if grapes else "varied grapes"
    style_str = style or "varied"
    return (
        f"For the appellation {name} in {region}, {country} "
        f"(style: {style_str}; grapes: {grape_str}), list the {PICKS_PER_AAV} highest-rated "
        "wineries by critical reputation. For each winery, include:\n"
        "- 'stars': 1.0-5.0 in 0.5 increments (overall rating)\n"
        "- 'note': one short sentence\n"
        "- 'varietals': up to 5 of the producer's best wines/varietals, "
        "each with a 'name', 'rating' (1.0-5.0, 0.5 increments) and short 'note'\n"
        "- 'vintages': up to 5 of the producer's best vintages (year as integer), "
        "each with a 'rating' on the 100-point critic scale and short 'note'\n\n"
        "Return JSON exactly in this shape: "
        '{"wineries": ['
        '{"name": "...", "stars": 4.5, "note": "...", '
        '"varietals": [{"name": "...", "rating": 4.5, "note": "..."}], '
        '"vintages":  [{"year": 2016, "rating": 96.0, "note": "..."}]}'
        ']}'
    )


async def upsert_rank(conn: asyncpg.Connection, appellation_id: str, rank: int) -> bool:
    """Apply popularity_rank to the appellation. Returns False if the AAV is unknown."""
    result = await conn.execute(
        "UPDATE appellations SET popularity_rank = $1 WHERE id = $2",
        rank, appellation_id,
    )
    # asyncpg returns e.g. "UPDATE 1" / "UPDATE 0"
    return result.endswith(" 1")


async def replace_ai_wineries(conn: asyncpg.Connection, appellation_id: str, wineries: list[dict]) -> int:
    """Replace the AI-sourced winery set for this AAV, returning the count inserted."""
    inserted = 0
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM wineries WHERE appellation_id = $1 AND source = 'ai'",
            appellation_id,
        )
        for w in wineries[:PICKS_PER_AAV]:
            name = w.get("name")
            if not name:
                continue
            stars = w.get("stars")
            note = w.get("note")
            winery_id = await conn.fetchval(
                """
                INSERT INTO wineries (appellation_id, name, stars, note, source, updated_at)
                VALUES ($1, $2, $3, $4, 'ai', NOW())
                RETURNING id
                """,
                appellation_id, name, stars, note,
            )
            inserted += 1

            for v in (w.get("varietals") or [])[:PICKS_PER_AAV]:
                vname = v.get("name")
                if not vname:
                    continue
                await conn.execute(
                    """
                    INSERT INTO winery_varietals (winery_id, varietal, rating, note, source)
                    VALUES ($1, $2, $3, $4, 'ai')
                    ON CONFLICT (winery_id, varietal) DO UPDATE
                      SET rating = EXCLUDED.rating,
                          note = EXCLUDED.note,
                          updated_at = NOW()
                    """,
                    winery_id, vname, v.get("rating"), v.get("note"),
                )

            for vt in (w.get("vintages") or [])[:PICKS_PER_AAV]:
                year = vt.get("year") or vt.get("vintage")
                if not isinstance(year, int):
                    continue
                await conn.execute(
                    """
                    INSERT INTO winery_vintages (winery_id, vintage, rating, note, source)
                    VALUES ($1, $2, $3, $4, 'ai')
                    ON CONFLICT (winery_id, vintage) DO UPDATE
                      SET rating = EXCLUDED.rating,
                          note = EXCLUDED.note,
                          updated_at = NOW()
                    """,
                    winery_id, year, vt.get("rating"), vt.get("note"),
                )
    return inserted


async def seed(limit: int | None, dry_run: bool) -> None:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(DATA_PATH.read_text())
    ranked_ids: list[str] = payload.get("ranked_appellation_ids", [])
    if not ranked_ids:
        print("popular_aavs.json has no ranked_appellation_ids", file=sys.stderr)
        sys.exit(1)
    if limit is not None:
        ranked_ids = ranked_ids[:limit]

    conn = await asyncpg.connect(settings.database_url)
    try:
        unknown: list[str] = []
        for rank, aid in enumerate(ranked_ids, start=1):
            row = await conn.fetchrow(
                """
                SELECT a.name, a.style, a.grapes,
                       r.name AS region_name, c.name AS country_name
                  FROM appellations a
                  JOIN regions r   ON r.id = a.region_id
                  JOIN countries c ON c.id = r.country_id
                 WHERE a.id = $1
                """,
                aid,
            )
            if row is None:
                unknown.append(aid)
                print(f"[{rank:>4}] {aid}  ✗ unknown appellation — skipping")
                continue

            print(f"[{rank:>4}] {aid}  ({row['country_name']} / {row['region_name']} / {row['name']})")
            if dry_run:
                continue

            await upsert_rank(conn, aid, rank)

            prompt = build_prompt(
                row["name"], row["region_name"], row["country_name"],
                row["style"], list(row["grapes"]) if row["grapes"] else [],
            )
            response = await call_sommelier(prompt, max_tokens=8192)
            wineries = response.get("wineries") if isinstance(response, dict) else None
            if not wineries:
                print(f"        skipped — bad response: {response}")
                await asyncio.sleep(RATE_LIMIT_SECONDS)
                continue

            inserted = await replace_ai_wineries(conn, aid, wineries)
            print(f"        inserted {inserted} wineries (+ varietals + vintages)")
            await asyncio.sleep(RATE_LIMIT_SECONDS)

        if unknown:
            print(f"\n{len(unknown)} unknown appellation ids skipped: {unknown[:5]}{'…' if len(unknown) > 5 else ''}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="don't call API or write rows")
    parser.add_argument("--limit", type=int, default=None, help="cap to first N AAVs")
    args = parser.parse_args()
    asyncio.run(seed(args.limit, args.dry_run))
