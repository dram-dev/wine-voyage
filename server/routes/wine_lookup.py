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
from server.wine_reference import resolve as resolve_local, stats as reference_stats
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
    # Place hints. The more the user has typed, the better the answer — an
    # unrecognized producer alongside "Napa Valley" still resolves a country,
    # a grape set and a drinking window.
    country: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=200)
    appellation: Optional[str] = Field(default=None, max_length=200)
    refresh: bool = Field(default=False, description="Bypass the cached answer")

    @model_validator(mode="after")
    def _producer_is_meaningful(self) -> "LookupRequest":
        if not normalize(self.producer):
            raise ValueError("producer must contain letters or digits")
        return self


@router.post("/wines/lookup")
async def lookup_wine(req: LookupRequest) -> dict:
    """Resolve a producer (+ vintage, cuvée, place hints) into full wine fields.

    Two sources, in this order:

      1. The offline reference (data/wine_reference.json) — deterministic, free,
         and authoritative about *where* a producer works.
      2. The model — broader, and better on a specific cuvée's grapes and window.

    They compound rather than compete: the reference sets the place, the model
    fills what the reference cannot, and either one alone still produces a
    usable answer. A model outage degrades the result, it does not fail it.
    """
    pool = get_pool()

    # Cheap, deterministic, and always available — do it first so there is
    # something to return even if the model call goes wrong.
    local = resolve_local(
        producer=req.producer, vintage=req.vintage, appellation=req.appellation,
        region=req.region, country=req.country,
    )

    digest = hashlib.sha256(
        json.dumps(
            {
                "p": normalize(req.producer), "v": req.vintage,
                "n": normalize(req.wine_name), "g": normalize(req.varietal),
                "c": normalize(req.country), "r": normalize(req.region),
                "a": normalize(req.appellation),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache_key = f"wine:lookup:{digest}"

    if not req.refresh:
        cached = await cache_get(pool, cache_key)
        if cached is not None:
            return {"cached": True, **cached}

    response = await call_sommelier(_prompt(req, local), max_tokens=2000, system=LOOKUP_SYSTEM_PROMPT)
    model_error = response.get("error") if isinstance(response, dict) else "bad response"

    result = _merge(local, {} if model_error else response, req, model_error)

    # Only a complete answer is worth caching, and never a failed model call.
    if result["found"] and not model_error:
        await cache_set(pool, cache_key, result)
    return {"cached": False, **result}


@router.get("/wines/reference")
async def reference_info() -> dict:
    """What the offline reference covers — so the UI can say what it knows."""
    return {"reference": reference_stats()}


def _prompt(req: LookupRequest, local: dict) -> str:
    known = [f"Producer: {req.producer.strip()}"]
    if req.vintage:
        known.append(f"Vintage: {req.vintage}")
    if req.wine_name:
        known.append(f"Cuvée / bottling: {req.wine_name.strip()}")
    if req.varietal:
        known.append(f"Varietal the user named: {req.varietal.strip()}")
    for label, value in (("Country", req.country), ("Region", req.region),
                         ("Appellation", req.appellation)):
        if value:
            known.append(f"{label} the user gave: {value.strip()}")

    # Telling the model what the reference already established keeps it from
    # contradicting a known fact, and focuses it on what is actually missing.
    if local.get("place"):
        known.append(
            f"(Our reference places this in {local['place']['name']}"
            f" — {local['wine'].get('region')}, {local['wine'].get('country')}."
            " Correct it only if you are confident it is wrong.)"
        )

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


# Fields the reference states as the *place's* norm rather than this wine's
# fact. A specific cuvée can differ — Ridge's Lytton Springs is Zinfandel from a
# Cabernet appellation — so a confident model answer wins on these. Place is the
# other way round: the reference is authoritative about where a producer works.
TYPICAL_FIELDS = {"varietals", "wine_type", "drink_from", "drink_to"}
PLACE_FIELDS = {"country", "region", "appellation"}


def _merge(local: dict, response: dict, req: LookupRequest, model_error: Optional[str]) -> dict:
    """Combine the reference and the model into one answer, tracking provenance.

    Precedence, highest first:
      the user's own typing  >  reference (place)  >  model  >  reference (typical)
    """
    model_wine = wine_fields(response.get("wine") or {}) if response else {}
    local_wine = local.get("wine") or {}
    wine: dict = {}
    sources: dict[str, str] = {}

    def put(field: str, value, source: str) -> None:
        if value in (None, "", []) or field in wine:
            return
        wine[field] = value
        sources[field] = source

    # 1. The reference owns the place when it recognized the producer or the
    #    user named somewhere real.
    for field in PLACE_FIELDS:
        put(field, local_wine.get(field), "reference")
    # 2. The model owns the specifics, and fills any place the reference missed.
    for field, value in model_wine.items():
        if field in ("producer", "wine_name", "vintage"):
            continue
        put(field, value, "model")
    # 3. The reference's typical values are the floor.
    for field in TYPICAL_FIELDS:
        put(field, local_wine.get(field), "reference-typical")
    # 4. Anything left the model knows.
    for field, value in model_wine.items():
        put(field, value, "model")

    wine.setdefault("bottle_size_ml", 750)

    # The user's own typing always wins, and the reference's spelling of a
    # producer beats the model's.
    wine["producer"] = (
        local.get("producer_name")
        if local.get("producer_match") in ("exact", "strong")
        else model_wine.get("producer") or req.producer.strip()
    )
    sources["producer"] = "reference" if local.get("producer_match") in ("exact", "strong") else "user"
    if req.wine_name:
        wine["wine_name"] = req.wine_name.strip(); sources["wine_name"] = "user"
    elif model_wine.get("wine_name"):
        wine["wine_name"] = model_wine["wine_name"]; sources["wine_name"] = "model"
    if req.vintage:
        wine["vintage"] = req.vintage; sources["vintage"] = "user"
    if req.varietal:
        wine["varietals"] = [req.varietal.strip()]; sources["varietals"] = "user"

    if wine.get("drink_from") and wine.get("drink_to") and wine["drink_from"] > wine["drink_to"]:
        wine["drink_from"], wine["drink_to"] = wine["drink_to"], wine["drink_from"]

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
    filled = [k for k, v in wine.items() if v not in (None, [], "") and k != "bottle_size_ml"]

    # "Found" means we produced something usable, from either source — not that
    # the model recognized the name. A reference hit alone is a good answer.
    found = bool(wine.get("country") or wine.get("region"))

    return {
        "found": found,
        "wine": wine,
        "sources": sources,
        "bottlings": bottlings,
        "estimated_value": value_estimate(response.get("estimated_value")) if response else None,
        "confidence": as_float(response.get("confidence"), 0, 1) if response else None,
        "field_confidence": field_confidence if isinstance(field_confidence, dict) else {},
        "vintage_note": as_str(response.get("vintage_note")) if response else None,
        "notes": _explain(local, req, found, model_error),
        "filled_fields": filled,
        "reference_match": local.get("producer_match"),
        "reference_place": local.get("place"),
        # Model or reference, this is still derived data: the form is pre-filled
        # for the user to confirm, never saved on its own.
        "needs_review": True,
        "model_error": model_error,
    }


def _explain(local: dict, req: LookupRequest, found: bool, model_error: Optional[str]) -> Optional[str]:
    """A sentence saying where the answer came from, or why there isn't one."""
    if model_error and not found:
        return (
            f"The producer isn't in the offline reference and the lookup service "
            f"could not be reached ({model_error}). Fill the rest in by hand — "
            "everything still saves normally."
        )
    if model_error:
        return (
            "Filled from the offline reference; the lookup service could not be "
            f"reached for the rest ({model_error})."
        )
    if not found:
        # The UI heading already names the producer; say what to do instead.
        if req.region or req.appellation:
            return "Not in the reference, and the place you gave wasn't recognized either."
        return (
            "Not in the reference. Naming a region or appellation usually resolves "
            "it — the country, grapes and drinking window all follow from the place."
        )
    if local.get("producer_match") in ("exact", "strong"):
        return None
    if local.get("place"):
        return f"Placed from “{local['place']['name']}” rather than the producer — check the region."
    return None
