"""Smoke test for /api/wines/lookup — the autofill behind manual bottle entry.

Runs the real app in-process against a real Postgres. The model call is stubbed,
so what is under test is the resolution logic, not the model:

  * the offline reference alone answering when the model is unreachable
  * an unrecognized producer still resolving from a region the user typed
  * the reference owning the place, the model owning the specifics
  * the user's own typing beating both

    pip install httpx
    DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_lookup

Exits non-zero if any check fails.
"""
import asyncio
import os
import sys

os.environ.setdefault("ANTHROPIC_API_KEY", "smoke-test-no-key")

import httpx

import server.routes.wine_lookup as wl
from server.main import app

fails = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond else f"  <- {detail}"))
    if not cond:
        fails.append(label)

async def dead_model(prompt, max_tokens=2000, system=None):
    return {"error": "Connection refused"}

async def _empty_impl(prompt, max_tokens=2000, system=None):
    """Model reachable but unhelpful — the common real case for obscure wines."""
    return {"found": False, "wine": {}, "bottlings": []}

def _empty():
    return _empty_impl(None)

async def good_model(prompt, max_tokens=2000, system=None):
    return {"found": True, "wine": {"producer":"Caymus Vineyards","wine_name":"Special Selection",
            "varietals":["Cabernet Sauvignon"],"wine_type":"red","country":"United States",
            "region":"Napa","appellation":"Rutherford","abv":14.8,"drink_from":2024,"drink_to":2040},
            "bottlings":[{"wine_name":"Special Selection","note":"Reserve bottling."}],
            "estimated_value":{"low":150,"mid":190,"high":240,"currency":"USD"},
            "confidence":0.9, "field_confidence":{"region":0.9}, "vintage_note":"Warm year."}

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            print("\n== model completely unavailable (was a hard 502 before) ==")
            wl.call_sommelier = dead_model
            r = await c.post("/api/wines/lookup", json={"producer":"Caymus","vintage":2019,"refresh":True})
            check("still 200", r.status_code==200, r.text[:200])
            d=r.json()
            check("found from the reference alone", d["found"] is True, r.text[:250])
            w=d["wine"]
            check("country filled offline", w["country"]=="United States", str(w))
            check("appellation filled offline", w["appellation"]=="Napa Valley", str(w))
            check("grapes filled offline", "Cabernet Sauvignon" in w["varietals"], str(w))
            check("window derived from vintage", (w["drink_from"],w["drink_to"])==(2023,2041), f"{w.get('drink_from')}-{w.get('drink_to')}")
            check("provenance recorded", d["sources"]["country"]=="reference", str(d["sources"])[:160])
            check("model outage surfaced", d["model_error"]=="Connection refused", str(d["model_error"]))
            check("note explains the degrade", "offline reference" in (d["notes"] or ""), str(d["notes"]))
            check("failed call not cached", d["cached"] is False)

            print("\n== unknown producer + a region the user typed ==")
            wl.call_sommelier = lambda *a, **k: _empty()   # model knows nothing either
            r = await c.post("/api/wines/lookup", json={"producer":"Nobody's Winery","vintage":2020,
                                                        "region":"Willamette Valley","refresh":True})
            d=r.json(); w=d["wine"]
            check("no longer returns nothing", d["found"] is True, r.text[:200])
            check("country inferred from region", w["country"]=="United States", str(w))
            check("grapes inferred from region", w["varietals"]==["Pinot Noir"], str(w.get("varietals")))
            check("producer echoed, not invented", w["producer"]=="Nobody's Winery", str(w["producer"]))
            check("note says it was placed by region", "Placed from" in (d["notes"] or "") or d["notes"] is None, str(d["notes"]))

            print("\n== truly nothing to go on ==")
            r = await c.post("/api/wines/lookup", json={"producer":"Zzz Qqq Xyz","vintage":2020,"refresh":True})
            d=r.json()
            check("found=false", d["found"] is False, r.text[:200])
            check("suggests adding a region", "region or appellation" in (d["notes"] or ""), str(d["notes"]))
            check("nothing invented", not d["wine"].get("country"), str(d["wine"]))

            print("\n== model available: it wins on specifics, reference on place ==")
            wl.call_sommelier = good_model
            r = await c.post("/api/wines/lookup", json={"producer":"Caymus","vintage":2019,"refresh":True})
            d=r.json(); w=d["wine"]
            check("reference keeps the appellation", w["appellation"]=="Napa Valley", str(w["appellation"]))
            check("reference spelling of producer", w["producer"]=="Caymus Vineyards", str(w["producer"]))
            check("model supplies abv", w["abv"]==14.8, str(w.get("abv")))
            check("model wins the drink window", (w["drink_from"],w["drink_to"])==(2024,2040), f"{w.get('drink_from')}-{w.get('drink_to')}")
            check("place provenance = reference", d["sources"]["appellation"]=="reference", str(d["sources"])[:200])
            check("abv provenance = model", d["sources"]["abv"]=="model", str(d["sources"])[:200])
            check("value estimate present", d["estimated_value"]["mid"]==190, str(d["estimated_value"]))
            check("no note needed on a clean hit", d["notes"] is None, str(d["notes"]))

            print("\n== user input still wins over both ==")
            r = await c.post("/api/wines/lookup", json={"producer":"Caymus","vintage":2021,
                                                        "wine_name":"My Bottling","varietal":"Merlot","refresh":True})
            w=r.json()["wine"]
            check("user vintage", w["vintage"]==2021, str(w["vintage"]))
            check("user cuvée", w["wine_name"]=="My Bottling", str(w["wine_name"]))
            check("user varietal", w["varietals"]==["Merlot"], str(w["varietals"]))

            print("\n== reference endpoint ==")
            r = await c.get("/api/wines/reference")
            check("reports coverage", r.json()["reference"]["producers"]>400, r.text[:150])

            await __import__("server.db", fromlist=["get_pool"]).get_pool().execute(
                "DELETE FROM ai_cache WHERE cache_key LIKE 'wine:lookup:%'")
    print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES: " + ", ".join(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
