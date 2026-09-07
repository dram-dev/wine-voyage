"""Fill in a wine from its producer and vintage.

Typing a bottle in by hand means eight fields, most of which follow from two:
who made it and when. This endpoint takes what the user has typed so far and
returns the rest — country, region, appellation, varietals, type, ABV, drinking
window, and a rough value.

Given only a producer and a vintage it also returns that producer's known
bottlings for the year, so the form can offer "which one?" instead of guessing.
Naming a cuvée narrows everything that follows.

Results are cached in `ai_cache` by the normalized query, so the same producer
and year costs one model call across every user of the instance.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from server.db import get_pool
from server.sommelier_client import cache_get, cache_set, call_sommelier
from server.wine_identity import normalize
from server.wine_parse import (
    WINE_TYPES,
    as_enum,
    as_float,
    as_str,
    as_str_list,
    value_estimate,
    wine_fields,
)

router = APIRouter(tags=["wine-lookup"])

LOOKUP_SYSTEM_PROMPT = (
    "You are a wine reference. You fill in what is known about a specific wine "
    "from a producer, a vintage, and whatever else the user has typed. "
    "Report only what you actually know. Use null for anything you are unsure "
    "of — a null field is far better than a plausible invention, because the "
    "user is about to save this into their cellar records. "
    "Respond ONLY with valid JSON matching the user's requested structure. "
    "No markdown, no preamble, no caveats."
)

MAX_BOTTLINGS = 12


class LookupRequest(BaseModel):
    producer: str = Field(..., min_length=2, max_length=300)
    vintage: Optional[int] = Field(default=None, ge=1800, le=2100)
    wine_name: Optional[str] = Field(default=None, max_length=300)
    varietal: Optional[str] = Field(default=None, max_length=200)
    refresh: bool = Field(default=False, description="Bypass the cached answer")

    @model_validator(mode="after")
    def _producer_is_meaningful(self) -> "LookupRequest":
        if not normalize(self.producer):
            raise ValueError("producer must contain letters or digits")
        return self


@router.post("/wines/lookup")
async def lookup_wine(req: LookupRequest) -> dict:
    """Resolve a producer (+ vintage, cuvée, varietal) into full wine fields."""
    pool = get_pool()

    # Cache on the normalized query so "Ch. Margaux" and "Chateau Margaux "
    # share an answer.
    digest = hashlib.sha256(
        json.dumps(
            {
                "p": normalize(req.producer),
                "v": req.vintage,
                "n": normalize(req.wine_name),
                "g": normalize(req.varietal),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache_key = f"wine:lookup:{digest}"

    if not req.refresh:
        cached = await cache_get(pool, cache_key)
        if cached is not None:
            return {"cached": True, **cached}

    response = await call_sommelier(_prompt(req), max_tokens=2000, system=LOOKUP_SYSTEM_PROMPT)
    if "error" in response:
        raise HTTPException(status_code=502, detail=f"lookup failed: {response['error']}")

    result = _normalize(response, req)
    if result["found"]:
        await cache_set(pool, cache_key, result)
    return {"cached": False, **result}


def _prompt(req: LookupRequest) -> str:
    known = [f"Producer: {req.producer.strip()}"]
    if req.vintage:
        known.append(f"Vintage: {req.vintage}")
    if req.wine_name:
        known.append(f"Cuvée / bottling: {req.wine_name.strip()}")
    if req.varietal:
        known.append(f"Varietal the user named: {req.varietal.strip()}")

    # With no cuvée named, the producer's range is the useful answer: the user
    # picks a bottling and the form re-asks with it.
    bottlings_instruction = (
        f"List up to {MAX_BOTTLINGS} of this producer's bottlings"
        + (f" made in {req.vintage}" if req.vintage else "")
        + ", most significant first, in `bottlings`. "
        if not req.wine_name
        else "The cuvée is known, so return `bottlings` as an empty array. "
    )

    return (
        "Fill in what is known about this wine.\n\n"
        + "\n".join(known)
        + "\n\n"
        + bottlings_instruction
        + "Fields in `wine` describe the specific bottling when one is named, "
        "otherwise what is true of the producer's range generally (their country, "
        "region and appellation are usually knowable from the producer alone).\n\n"
        "Return JSON in exactly this shape:\n"
        "{\n"
        '  "found": true,\n'
        '  "wine": {\n'
        '    "producer": "the correctly spelled full producer name",\n'
        '    "wine_name": "cuvée, or null if not known",\n'
        '    "vintage": 2015,\n'
        '    "varietals": ["Cabernet Sauvignon"],\n'
        '    "wine_type": "red|white|rose|sparkling|dessert|fortified|other",\n'
        '    "country": "France",\n'
        '    "region": "Bordeaux",\n'
        '    "appellation": "Margaux",\n'
        '    "bottle_size_ml": 750,\n'
        '    "abv": 13.5,\n'
        '    "drink_from": 2028,\n'
        '    "drink_to": 2055\n'
        "  },\n"
        '  "bottlings": [{"wine_name": "Grand Vin", "varietals": ["..."], '
        '"wine_type": "red", "note": "one short line on what it is"}],\n'
        '  "estimated_value": {"low": 0, "mid": 0, "high": 0, "currency": "USD"},\n'
        '  "confidence": 0.0,\n'
        '  "field_confidence": {"region": 0.9, "varietals": 0.8, "drink_from": 0.5},\n'
        '  "vintage_note": "one line on how this vintage went in this region, or null",\n'
        '  "notes": "anything the user should check, or null"\n'
        "}\n\n"
        "Rules:\n"
        "- `found` is false if you do not recognize this producer at all. Do not "
        "invent a region for a producer you have never heard of.\n"
        "- Correct obvious misspellings of the producer in `wine.producer`.\n"
        "- `varietals`: what is actually in the bottle, or the appellation's "
        "required grapes. Empty array if you cannot say.\n"
        "- `drink_from` / `drink_to`: your assessment for this wine and vintage. "
        "Null if you cannot judge it.\n"
        "- `estimated_value`: typical current retail per bottle. Null if unknown.\n"
        "- `field_confidence`: 0-1 per field you filled, so the user knows what to "
        "double-check.\n"
    )


def _normalize(response: dict, req: LookupRequest) -> dict:
    wine = wine_fields(response.get("wine") or {})

    # The user's own typing always wins over the model's version of it.
    wine["producer"] = wine["producer"] or req.producer.strip()
    if req.wine_name:
        wine["wine_name"] = req.wine_name.strip()
    if req.vintage:
        wine["vintage"] = req.vintage
    if req.varietal and not wine["varietals"]:
        wine["varietals"] = [req.varietal.strip()]

    bottlings = []
    for entry in (response.get("bottlings") or [])[:MAX_BOTTLINGS]:
        if not isinstance(entry, dict):
            continue
        name = as_str(entry.get("wine_name"))
        if not name:
            continue
        bottlings.append({
            "wine_name": name,
            "varietals": as_str_list(entry.get("varietals"))[:12],
            "wine_type": as_enum(entry.get("wine_type"), WINE_TYPES),
            "note": as_str(entry.get("note")),
        })

    field_confidence = response.get("field_confidence")
    filled = [key for key, value in wine.items() if value not in (None, [], "")]

    return {
        # A reply with no country and no region has told us nothing usable,
        # whatever it claims about `found`.
        "found": bool(response.get("found", True)) and bool(wine["country"] or wine["region"]),
        "wine": wine,
        "bottlings": bottlings,
        "estimated_value": value_estimate(response.get("estimated_value")),
        "confidence": as_float(response.get("confidence"), 0, 1),
        "field_confidence": field_confidence if isinstance(field_confidence, dict) else {},
        "vintage_note": as_str(response.get("vintage_note")),
        "notes": as_str(response.get("notes")),
        "filled_fields": filled,
        # Model-derived, like a label scan: the form is pre-filled for the user
        # to confirm, never saved on its own.
        "needs_review": True,
    }
