"""Populate the wineries table by asking Claude for 15 notable producers per appellation.

Cost is roughly $2-3 across all appellations. Use --dry-run to preview without
hitting the API or writing rows.

    python -m scripts.seed_wineries            # real run
    python -m scripts.seed_wineries --dry-run  # no API calls, no writes
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

from server.config import settings
from server.sommelier_client import call_sommelier

RATE_LIMIT_SECONDS = 1.0


def build_prompt(name: str, region: str, country: str, style: str | None, grapes: list[str]) -> str:
    grape_str = ", ".join(grapes) if grapes else "varied grapes"
    style_str = style or "varied"
    return (
        f"List 15 notable wineries in {name}, {region}, {country} "
        f"(style: {style_str}; grapes: {grape_str}). "
        "Include a star rating from 1.0 to 5.0 in 0.5 increments based on critical "
        "reputation, and a one-sentence note. "
        'Return JSON exactly in this shape: '
        '{"wineries": [{"name": "...", "stars": 4.5, "note": "..."}]}'
    )


async def seed(dry_run: bool) -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT a.id, a.name, a.style, a.grapes,
                   r.name AS region_name, c.name AS country_name
              FROM appellations a
              JOIN regions r   ON r.id = a.region_id
              JOIN countries c ON c.id = r.country_id
              ORDER BY c.name, r.name, a.name
            """
        )
        if not rows:
            print("no appellations found — run seed_appellations.py first", file=sys.stderr)
            sys.exit(1)

        for row in rows:
            print(f"-> {row['country_name']} / {row['region_name']} / {row['name']}")
            if dry_run:
                continue

            prompt = build_prompt(
                row["name"], row["region_name"], row["country_name"],
                row["style"], list(row["grapes"]) if row["grapes"] else [],
            )
            response = await call_sommelier(prompt, max_tokens=2048)
            wineries = response.get("wineries") if isinstance(response, dict) else None
            if not wineries:
                print(f"   skipped (response: {response})")
                await asyncio.sleep(RATE_LIMIT_SECONDS)
                continue

            async with conn.transaction():
                for w in wineries:
                    name = w.get("name")
                    if not name:
                        continue
                    stars = w.get("stars")
                    note = w.get("note")
                    await conn.execute(
                        """
                        INSERT INTO wineries (appellation_id, name, stars, note, source, updated_at)
                        VALUES ($1, $2, $3, $4, 'ai', NOW())
                        """,
                        row["id"], name, stars, note,
                    )
            print(f"   inserted {len(wineries)} wineries")
            await asyncio.sleep(RATE_LIMIT_SECONDS)
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="don't call API or write rows")
    args = parser.parse_args()
    asyncio.run(seed(args.dry_run))
