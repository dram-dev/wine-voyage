"""Backfill lat/lng on wineries via Claude.

Wineries seeded by `scripts/seed_top_rated.py` have names but no coordinates.
This script asks Claude for approximate coordinates in batches per appellation,
which keeps prompts small and lets the model anchor on the AAV's location.

    python -m scripts.seed_winery_geo --dry-run            # preview
    python -m scripts.seed_winery_geo --limit-aavs 25      # first 25 AAVs only
    python -m scripts.seed_winery_geo                      # full pass

The script only touches rows where `lat IS NULL OR lng IS NULL`, so it is
safe to re-run after partial failures.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import asyncpg

from server.config import settings
from server.sommelier_client import call_sommelier

RATE_LIMIT_SECONDS = 1.0


def build_prompt(appellation: str, region: str, country: str, names: list[str]) -> str:
    listing = "\n".join(f"- {n}" for n in names)
    return (
        f"For each of the wineries below located in {appellation}, {region}, {country}, "
        "return approximate decimal latitude and longitude (WGS84, ~4 decimal places). "
        "If a winery cannot be located confidently, return null for both fields.\n\n"
        f"Wineries:\n{listing}\n\n"
        'Return JSON exactly in this shape: '
        '{"coords": [{"name": "...", "lat": 47.1234, "lng": 4.9876}]}'
    )


async def seed(limit_aavs: int | None, dry_run: bool) -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        aavs = await conn.fetch(
            """
            SELECT a.id, a.name, r.name AS region_name, c.name AS country_name,
                   array_agg(w.name ORDER BY w.id) AS winery_names,
                   array_agg(w.id   ORDER BY w.id) AS winery_ids
              FROM appellations a
              JOIN regions r   ON r.id = a.region_id
              JOIN countries c ON c.id = r.country_id
              JOIN wineries w  ON w.appellation_id = a.id
             WHERE w.lat IS NULL OR w.lng IS NULL
             GROUP BY a.id, a.name, r.name, c.name, a.popularity_rank
             ORDER BY a.popularity_rank NULLS LAST, a.name
            """
        )
        if not aavs:
            print("no wineries missing coordinates — nothing to do")
            return
        if limit_aavs is not None:
            aavs = aavs[:limit_aavs]

        for i, row in enumerate(aavs, start=1):
            names: list[str] = list(row["winery_names"])
            ids: list[int] = list(row["winery_ids"])
            id_by_name = {n: wid for n, wid in zip(names, ids)}

            print(f"[{i:>4}/{len(aavs)}] {row['country_name']} / {row['region_name']} / {row['name']} ({len(names)} wineries)")
            if dry_run:
                continue

            prompt = build_prompt(row["name"], row["region_name"], row["country_name"], names)
            response = await call_sommelier(prompt, max_tokens=4096)
            coords = response.get("coords") if isinstance(response, dict) else None
            if not coords:
                print(f"        skipped — bad response: {response}")
                await asyncio.sleep(RATE_LIMIT_SECONDS)
                continue

            updated = 0
            async with conn.transaction():
                for c in coords:
                    name = c.get("name")
                    lat = c.get("lat")
                    lng = c.get("lng")
                    if not name or lat is None or lng is None:
                        continue
                    winery_id = id_by_name.get(name)
                    if winery_id is None:
                        continue
                    await conn.execute(
                        "UPDATE wineries SET lat = $1, lng = $2 WHERE id = $3",
                        lat, lng, winery_id,
                    )
                    updated += 1
            print(f"        updated {updated} winery coordinates")
            await asyncio.sleep(RATE_LIMIT_SECONDS)
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="don't call API or write rows")
    parser.add_argument("--limit-aavs", type=int, default=None, help="cap to first N AAVs")
    args = parser.parse_args()
    try:
        asyncio.run(seed(args.limit_aavs, args.dry_run))
    except KeyboardInterrupt:
        sys.exit(130)
