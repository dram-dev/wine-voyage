"""Label photo recognition: snap the bottle, skip the typing.

POST an image of a wine label and get back the fields the add-bottle form
needs — producer, cuvée, vintage, varietals, region, appellation, bottle size,
ABV — plus a drink window and a rough market value, each with its own
confidence so the UI can flag what the user should double-check.

Results are cached by SHA-256 of the image bytes, so re-scanning the same photo
(or the same bottle from a second phone) costs nothing.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.db import get_pool
from server.sommelier_client import call_sommelier_vision
from server.wine_parse import as_float, as_str, value_estimate, wine_fields

router = APIRouter(tags=["labels"])
logger = logging.getLogger(__name__)

SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # Anthropic's per-image ceiling

_DATA_URL = re.compile(r"^data:(?P<media_type>[\w.+/-]+);base64,(?P<data>.*)$", re.DOTALL)

IDENTIFY_PROMPT = """Identify the wine in this bottle label photograph.

Return JSON in exactly this shape:
{
  "producer": "string or null",
  "wine_name": "cuvee or bottling name, or null",
  "vintage": 2019,
  "varietals": ["Cabernet Sauvignon"],
  "wine_type": "red|white|rose|sparkling|dessert|fortified|other",
  "country": "string or null",
  "region": "string or null",
  "appellation": "string or null",
  "bottle_size_ml": 750,
  "abv": 13.5,
  "drink_from": 2024,
  "drink_to": 2035,
  "confidence": 0.0,
  "field_confidence": {"producer": 0.0, "vintage": 0.0, "region": 0.0},
  "estimated_value": {"low": 0, "mid": 0, "high": 0, "currency": "USD"},
  "readable": true,
  "notes": "anything ambiguous about the label"
}

Rules:
- Read the label. Do not guess a producer or vintage that is not visible or
  strongly implied by the label design.
- Non-vintage bottlings: vintage is null.
- varietals: from the label if stated, otherwise the appellation's legally
  required grapes; empty array if neither applies.
- drink_from / drink_to: your assessment of the drinking window for this wine
  and vintage. Null if you cannot judge it.
- estimated_value: typical current retail per bottle, your best estimate. Null
  if you have no basis for one.
- confidence: 0-1, how sure you are of the overall identification.
- readable: false if the photo is too blurry, dark, or cropped to identify.
"""


class IdentifyRequest(BaseModel):
    image_base64: str = Field(..., min_length=32, description="Raw base64, or a data: URL")
    media_type: Optional[str] = Field(default=None, description="Inferred from a data: URL if omitted")
    account_id: Optional[str] = Field(default=None, max_length=128)
    refresh: bool = Field(default=False, description="Bypass the cached result for this image")


@router.post("/labels/identify")
async def identify_label(req: IdentifyRequest) -> dict:
    media_type, raw_b64 = _split_image(req.image_base64, req.media_type)
    try:
        image_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="image_base64 is not valid base64")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"image is {len(image_bytes) // 1024}KB; resize to under {MAX_IMAGE_BYTES // 1024}KB",
        )

    digest = hashlib.sha256(image_bytes).hexdigest()
    pool = get_pool()

    if not req.refresh:
        cached = await pool.fetchval("SELECT result FROM label_scans WHERE image_sha256 = $1", digest)
        if cached is not None:
            result = cached if isinstance(cached, dict) else json.loads(cached)
            return {"cached": True, "image_sha256": digest, **result}

    response = await call_sommelier_vision(IDENTIFY_PROMPT, [(media_type, raw_b64)])
    if "error" in response:
        raise HTTPException(status_code=502, detail=f"label recognition failed: {response['error']}")

    result = _normalize(response)
    if result["readable"]:
        await pool.execute(
            """
            INSERT INTO label_scans (image_sha256, account_id, result)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (image_sha256) DO UPDATE
              SET result = EXCLUDED.result, created_at = NOW()
            """,
            digest, req.account_id, json.dumps(result),
        )

    return {"cached": False, "image_sha256": digest, **result}


def _split_image(image: str, media_type: Optional[str]) -> tuple[str, str]:
    """Accept either a bare base64 payload or a full `data:` URL."""
    match = _DATA_URL.match(image.strip())
    if match:
        media_type = media_type or match.group("media_type")
        image = match.group("data")
    media_type = (media_type or "image/jpeg").lower()
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"media_type must be one of: {', '.join(sorted(SUPPORTED_MEDIA_TYPES))}",
        )
    return media_type, image.strip()


def _normalize(response: dict) -> dict:
    """Coerce the model's reply into the shape the add-bottle form expects."""
    field_confidence = response.get("field_confidence")
    wine = wine_fields(response)
    return {
        "wine": wine,
        # A reply with no producer is not a reading of a label, whatever the
        # model says about `readable`.
        "readable": bool(response.get("readable", True)) and bool(wine["producer"]),
        "confidence": as_float(response.get("confidence"), 0, 1),
        "field_confidence": field_confidence if isinstance(field_confidence, dict) else {},
        "estimated_value": value_estimate(response.get("estimated_value")),
        "notes": as_str(response.get("notes")),
        # Everything here is read off a photo by a model. The UI shows the form
        # pre-filled for the user to confirm, never saved silently.
        "needs_review": True,
    }
