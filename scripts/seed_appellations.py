"""Idempotently load countries / regions / appellations from data/appellations.json.

Run once after applying the SQL migrations:

    python -m scripts.seed_appellations
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

from server.config import settings

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "appellations.json"


async def seed() -> None:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(DATA_PATH.read_text())
    countries = payload.get("countries", [])

    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            n_countries = n_regions = n_appellations = 0
            for country in countries:
                await conn.execute(
                    """
                    INSERT INTO countries (id, name, emoji, color)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (id) DO UPDATE
                      SET name = EXCLUDED.name,
                          emoji = EXCLUDED.emoji,
                          color = EXCLUDED.color
                    """,
                    country["id"], country["name"],
                    country.get("emoji"), country.get("color"),
                )
                n_countries += 1

                for region in country.get("regions", []):
                    await conn.execute(
                        """
                        INSERT INTO regions (id, country_id, name)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (id) DO UPDATE
                          SET country_id = EXCLUDED.country_id,
                              name = EXCLUDED.name
                        """,
                        region["id"], country["id"], region["name"],
                    )
                    n_regions += 1

                    for app in region.get("appellations", []):
                        await conn.execute(
                            """
                            INSERT INTO appellations (id, region_id, name, grapes, style, lat, lng)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (id) DO UPDATE
                              SET region_id = EXCLUDED.region_id,
                                  name = EXCLUDED.name,
                                  grapes = EXCLUDED.grapes,
                                  style = EXCLUDED.style,
                                  lat = EXCLUDED.lat,
                                  lng = EXCLUDED.lng
                            """,
                            app["id"], region["id"], app["name"],
                            app.get("grapes", []), app.get("style"),
                            app.get("lat"), app.get("lng"),
                        )
                        n_appellations += 1

        print(f"seeded {n_countries} countries / {n_regions} regions / {n_appellations} appellations")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
