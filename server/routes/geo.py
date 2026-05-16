"""Geo / map endpoint for wineries and AAVs.

GET /api/geo/features returns a GeoJSON FeatureCollection for a viewport
(bounding box + zoom). Level of detail scales with zoom:

    zoom <  7   - appellations only (continental view)
    7 <= z < 11 - appellations + premium wineries (stars >= 4.5)
    zoom >= 11  - appellations + all wineries with coordinates

The frontend (Leaflet / Mapbox / react-map-gl) drives the actual pan/zoom UX;
this endpoint returns the right density of features for the current viewport.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from server.db import get_pool

router = APIRouter(tags=["geo"])

ZOOM_APPELLATIONS_ONLY = 7
ZOOM_ALL_WINERIES = 11
PREMIUM_STAR_THRESHOLD = 4.5

DEFAULT_LIMIT = 1500
MAX_LIMIT = 5000


@router.get("/geo/features")
async def geo_features(
    north: float = Query(..., ge=-90.0, le=90.0),
    south: float = Query(..., ge=-90.0, le=90.0),
    east: float = Query(..., ge=-180.0, le=180.0),
    west: float = Query(..., ge=-180.0, le=180.0),
    zoom: int = Query(..., ge=0, le=22, description="Map zoom level (0=world, 22=street)"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> dict:
    if north <= south:
        raise HTTPException(status_code=400, detail="north must be greater than south")

    pool = get_pool()
    # west > east means the bounding box wraps the date line — switch the lng
    # predicate from a BETWEEN range to a disjunction.
    if west > east:
        appellation_lng = "(a.lng >= $3 OR a.lng <= $4)"
        winery_lng = "(w.lng >= $3 OR w.lng <= $4)"
    else:
        appellation_lng = "a.lng BETWEEN $3 AND $4"
        winery_lng = "w.lng BETWEEN $3 AND $4"

    features: list[dict] = []

    appellation_rows = await pool.fetch(
        f"""
        SELECT a.id, a.name, a.style, a.grapes, a.popularity_rank,
               a.lat, a.lng,
               r.id AS region_id, r.name AS region_name,
               c.id AS country_id, c.name AS country_name, c.emoji AS country_emoji,
               COALESCE(wc.cnt, 0) AS winery_count
          FROM appellations a
          JOIN regions r   ON r.id = a.region_id
          JOIN countries c ON c.id = r.country_id
          LEFT JOIN (
              SELECT appellation_id, COUNT(*) AS cnt
                FROM wineries
               GROUP BY appellation_id
          ) wc ON wc.appellation_id = a.id
         WHERE a.lat IS NOT NULL AND a.lng IS NOT NULL
           AND a.lat BETWEEN $1 AND $2
           AND {appellation_lng}
         ORDER BY a.popularity_rank NULLS LAST, a.name
         LIMIT $5
        """,
        south, north, west, east, limit,
    )
    for row in appellation_rows:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row["lng"]), float(row["lat"])]},
            "properties": {
                "kind": "appellation",
                "id": row["id"],
                "name": row["name"],
                "style": row["style"],
                "grapes": list(row["grapes"]) if row["grapes"] else [],
                "popularity_rank": row["popularity_rank"],
                "winery_count": row["winery_count"],
                "region": {"id": row["region_id"], "name": row["region_name"]},
                "country": {
                    "id": row["country_id"],
                    "name": row["country_name"],
                    "emoji": row["country_emoji"],
                },
            },
        })

    kind = "appellations"
    if zoom >= ZOOM_APPELLATIONS_ONLY:
        kind = "mixed"
        remaining = max(0, limit - len(features))
        if remaining:
            min_stars = None if zoom >= ZOOM_ALL_WINERIES else PREMIUM_STAR_THRESHOLD
            winery_rows = await pool.fetch(
                f"""
                SELECT w.id, w.name, w.stars, w.note, w.lat, w.lng,
                       w.appellation_id, a.name AS appellation_name
                  FROM wineries w
                  JOIN appellations a ON a.id = w.appellation_id
                 WHERE w.lat IS NOT NULL AND w.lng IS NOT NULL
                   AND w.lat BETWEEN $1 AND $2
                   AND {winery_lng}
                   AND ($6::numeric IS NULL OR w.stars >= $6)
                 ORDER BY w.stars DESC NULLS LAST, w.name
                 LIMIT $5
                """,
                south, north, west, east, remaining, min_stars,
            )
            for row in winery_rows:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(row["lng"]), float(row["lat"])]},
                    "properties": {
                        "kind": "winery",
                        "id": row["id"],
                        "name": row["name"],
                        "stars": float(row["stars"]) if row["stars"] is not None else None,
                        "note": row["note"],
                        "appellation": {"id": row["appellation_id"], "name": row["appellation_name"]},
                    },
                })

    return {
        "type": "FeatureCollection",
        "zoom": zoom,
        "kind": kind,
        "bbox": [west, south, east, north],
        "thresholds": {
            "appellations_only_below": ZOOM_APPELLATIONS_ONLY,
            "all_wineries_at_or_above": ZOOM_ALL_WINERIES,
            "premium_star_threshold": PREMIUM_STAR_THRESHOLD,
        },
        "count": len(features),
        "features": features,
    }


@router.get("/geo/appellation/{appellation_id}")
async def appellation_geo(appellation_id: str) -> dict:
    """All wineries (with coordinates) for a single appellation. Useful at the
    deepest zoom level when the user has drilled into one AAV."""
    pool = get_pool()
    app_row = await pool.fetchrow(
        """
        SELECT a.id, a.name, a.lat, a.lng,
               r.id AS region_id, r.name AS region_name,
               c.id AS country_id, c.name AS country_name, c.emoji AS country_emoji
          FROM appellations a
          JOIN regions r   ON r.id = a.region_id
          JOIN countries c ON c.id = r.country_id
         WHERE a.id = $1
        """,
        appellation_id,
    )
    if app_row is None:
        raise HTTPException(status_code=404, detail="appellation not found")

    winery_rows = await pool.fetch(
        """
        SELECT id, name, stars, note, lat, lng
          FROM wineries
         WHERE appellation_id = $1 AND lat IS NOT NULL AND lng IS NOT NULL
         ORDER BY stars DESC NULLS LAST, name
        """,
        appellation_id,
    )

    return {
        "type": "FeatureCollection",
        "appellation": {
            "id": app_row["id"],
            "name": app_row["name"],
            "center": (
                [float(app_row["lng"]), float(app_row["lat"])]
                if app_row["lat"] is not None and app_row["lng"] is not None
                else None
            ),
            "region": {"id": app_row["region_id"], "name": app_row["region_name"]},
            "country": {
                "id": app_row["country_id"],
                "name": app_row["country_name"],
                "emoji": app_row["country_emoji"],
            },
        },
        "count": len(winery_rows),
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(r["lng"]), float(r["lat"])]},
                "properties": {
                    "kind": "winery",
                    "id": r["id"],
                    "name": r["name"],
                    "stars": float(r["stars"]) if r["stars"] is not None else None,
                    "note": r["note"],
                },
            }
            for r in winery_rows
        ],
    }
