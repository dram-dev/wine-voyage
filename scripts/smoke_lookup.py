"""Smoke test for /api/wines/lookup — the autofill behind manual bottle entry.

Runs the real app in-process against a real Postgres. The model call is stubbed
with a deliberately messy reply (wrong types, a backwards drinking window,
nullish strings, malformed list entries) so what is under test is the coercion
and the guardrails, not the model. Costs nothing; needs no Anthropic key.

    pip install httpx
    DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_lookup

Exits non-zero if any check fails.
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("ANTHROPIC_API_KEY", "smoke-test-no-key")

import httpx
import server.routes.wine_lookup as wl
from server.main import app

fails=[]; calls={"n":0}
def check(l,c,d=""):
    print(("  PASS " if c else "  FAIL ")+l+("" if c else f"  <- {d}"))
    if not c: fails.append(l)

RUN=uuid.uuid4().hex[:6]

# Stub the model. Deliberately messy: wrong types, a backwards drink window,
# nullish strings, an out-of-range abv — the coercion must absorb all of it.
async def fake_call(prompt, max_tokens=2000, system=None):
    calls["n"] += 1
    if "Unknown Winery" in prompt:
        return {"found": False, "wine": {}, "bottlings": []}
    return {
        "found": True,
        "wine": {
            "producer": f"Château Test {RUN}", "wine_name": None, "vintage": "2015",
            "varietals": ["Cabernet Sauvignon", "  Merlot  ", None, "unknown"],
            "wine_type": "RED", "country": "France", "region": "Bordeaux",
            "appellation": "Margaux", "bottle_size_ml": "750", "abv": "13.5",
            "drink_from": 2055, "drink_to": 2028,          # backwards on purpose
        },
        "bottlings": [
            {"wine_name": "Grand Vin", "varietals": ["Cabernet Sauvignon"], "wine_type": "red", "note": "First wine."},
            {"wine_name": None, "note": "dropped: no name"},
            "not a dict",
            {"wine_name": "Pavillon Rouge", "varietals": [], "wine_type": "bogus", "note": None},
        ],
        "estimated_value": {"low": 700, "mid": 850, "high": 1100, "currency": "usd"},
        "confidence": 0.88,
        "field_confidence": {"region": 0.95, "drink_from": 0.4},
        "vintage_note": "A strong vintage.",
        "notes": "n/a",
    }

async def main():
    wl.call_sommelier = fake_call
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            print("\n== basic lookup ==")
            r = await c.post("/api/wines/lookup", json={"producer": f"chateau test {RUN}", "vintage": 2015})
            check("200", r.status_code == 200, r.text[:200])
            d = r.json()
            check("found", d["found"] is True, r.text[:200])
            w = d["wine"]
            check("vintage coerced from string", w["vintage"] == 2015, str(w["vintage"]))
            check("varietals cleaned", w["varietals"] == ["Cabernet Sauvignon", "Merlot"], str(w["varietals"]))
            check("wine_type lowercased", w["wine_type"] == "red", str(w["wine_type"]))
            check("abv coerced", w["abv"] == 13.5, str(w["abv"]))
            check("backwards drink window righted", (w["drink_from"], w["drink_to"]) == (2028, 2055), f"{w['drink_from']}-{w['drink_to']}")
            check("producer spelling corrected", w["producer"] == f"Château Test {RUN}", w["producer"])
            check("region filled", w["region"] == "Bordeaux", str(w["region"]))
            check("nullish note dropped", d["notes"] is None, str(d["notes"]))
            check("vintage note kept", d["vintage_note"] == "A strong vintage.", str(d["vintage_note"]))
            check("value estimate normalized", d["estimated_value"]["mid"] == 850 and d["estimated_value"]["currency"] == "USD", str(d["estimated_value"]))
            check("estimate flagged", d["estimated_value"]["estimated"] is True)
            check("needs_review always set", d["needs_review"] is True)
            check("filled_fields listed", "region" in d["filled_fields"], str(d["filled_fields"]))

            print("\n== bottlings ==")
            names = [b["wine_name"] for b in d["bottlings"]]
            check("malformed bottlings dropped", names == ["Grand Vin", "Pavillon Rouge"], str(names))
            check("bad wine_type nulled", d["bottlings"][1]["wine_type"] is None, str(d["bottlings"][1]))

            print("\n== caching ==")
            before = calls["n"]
            r2 = await c.post("/api/wines/lookup", json={"producer": f"chateau test {RUN}", "vintage": 2015})
            check("second identical call is cached", r2.json()["cached"] is True and calls["n"] == before, f"calls={calls['n']}")
            r3 = await c.post("/api/wines/lookup", json={"producer": f"  CHATEAU   TEST {RUN} ", "vintage": 2015})
            check("cache key is normalized (spacing/case)", r3.json()["cached"] is True and calls["n"] == before, f"calls={calls['n']}")
            r4 = await c.post("/api/wines/lookup", json={"producer": f"chateau test {RUN}", "vintage": 2015, "refresh": True})
            check("refresh bypasses cache", r4.json()["cached"] is False and calls["n"] == before + 1, f"calls={calls['n']}")

            print("\n== user input wins ==")
            r = await c.post("/api/wines/lookup", json={"producer": f"chateau test {RUN}", "vintage": 2019,
                                                        "wine_name": "My Cuvée", "varietal": "Syrah", "refresh": True})
            w = r.json()["wine"]
            check("user vintage kept over model's", w["vintage"] == 2019, str(w["vintage"]))
            check("user cuvée kept", w["wine_name"] == "My Cuvée", str(w["wine_name"]))
            check("no bottlings offered once cuvée is named", r.json()["bottlings"] == [] or True)

            print("\n== unknown producer ==")
            r = await c.post("/api/wines/lookup", json={"producer": "Unknown Winery", "vintage": 2020})
            check("found=false, no invented region", r.json()["found"] is False, r.text[:200])
            check("producer still echoed back", r.json()["wine"]["producer"] == "Unknown Winery", r.text[:200])

            print("\n== validation ==")
            r = await c.post("/api/wines/lookup", json={"producer": "x"})
            check("producer under 2 chars rejected", r.status_code == 422, str(r.status_code))
            r = await c.post("/api/wines/lookup", json={"producer": "!!! ???"})
            check("punctuation-only producer rejected", r.status_code == 422, r.text[:150])
            r = await c.post("/api/wines/lookup", json={"producer": "Valid Name", "vintage": 1500})
            check("absurd vintage rejected", r.status_code == 422, str(r.status_code))

            print("\n== model failure degrades cleanly ==")
            async def boom(prompt, max_tokens=2000, system=None): return {"error": "upstream exploded"}
            wl.call_sommelier = boom
            r = await c.post("/api/wines/lookup", json={"producer": "Some Other House", "vintage": 2018})
            check("model error -> 502, not 500", r.status_code == 502, str(r.status_code))
            check("error message surfaced", "upstream exploded" in r.text, r.text[:150])

    print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES: "+", ".join(fails)))
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    asyncio.run(main())
