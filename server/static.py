"""Serve the built React frontend from the same process as the API.

`web/dist` is mounted so uvicorn hands out the app and `/api` from one origin:
no CORS, and the frontend needs no VITE_API_BASE because `/api/sommelier` is
already a same-origin path. If the bundle has not been built the API still
starts normally and only logs a hint.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def mount_frontend(app: FastAPI) -> None:
    """Mount web/dist. Must be called after every API router is registered,
    because the SPA fallback below is a catch-all and route order decides."""
    index = WEB_DIST / "index.html"
    if not index.is_file():
        logger.info(
            "No frontend bundle at %s — serving the API only. "
            "Build it with: cd web && npm install && npm run build",
            WEB_DIST,
        )
        return

    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        # Unmatched /api paths are API 404s, not the app shell.
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        if path:
            candidate = (WEB_DIST / path).resolve()
            if candidate.is_file() and candidate.is_relative_to(WEB_DIST):
                return FileResponse(candidate)

        # Anything else is a client-side route: hand back the app shell.
        return FileResponse(index)

    logger.info("Serving frontend from %s", WEB_DIST)
