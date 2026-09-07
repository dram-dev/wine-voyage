"""End-to-end smoke test for the cellar inventory API.

Runs the real FastAPI app in-process against a real Postgres — no server, no
network. Creates two throwaway accounts, exercises every cellar and bottle
endpoint, and deletes what it made.

    pip install httpx
    DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_cellar

Exits non-zero if any check fails.
"""
import asyncio
import os
import sys
import uuid

# The AI-backed endpoints are checked for clean failure, not for real answers,
# so a placeholder key is enough when one is not already set.
os.environ.setdefault("ANTHROPIC_API_KEY", "smoke-test-no-key")

import httpx

from server.main import app

# Unique per run so a failed run never poisons the next one.
RUN = uuid.uuid4().hex[:8]
ACC = f"smoke-{RUN}-a"
OTHER = f"smoke-{RUN}-b"
fails = []

def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond else f"  <- {detail}"))
    if not cond: fails.append(label)

async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            print("\n== cellars ==")
            r = await c.post("/api/cellars", json={"account_id": ACC, "name": "Main Cellar", "location": "Basement", "capacity": 300})
            check("create cellar 201", r.status_code == 201, r.text)
            main_id = r.json()["id"]
            check("first cellar auto-default", r.json()["is_default"] is True, r.text)

            r = await c.post("/api/cellars", json={"account_id": ACC, "name": "Office Rack", "capacity": 24})
            office_id = r.json()["id"]
            check("second cellar not default", r.json()["is_default"] is False)

            r = await c.post("/api/cellars", json={"account_id": ACC, "name": "Main Cellar"})
            check("duplicate name 409", r.status_code == 409, r.text)

            r = await c.get("/api/cellars", params={"account_id": ACC})
            check("list two cellars", len(r.json()) == 2, r.text)

            r = await c.get("/api/cellars", params={"account_id": OTHER})
            check("other account sees none", r.json() == [], r.text)

            r = await c.patch(f"/api/cellars/{office_id}", params={"account_id": ACC}, json={"is_default": True})
            check("patch sets default", r.json()["is_default"] is True, r.text)
            r = await c.get("/api/cellars", params={"account_id": ACC})
            defaults = [x for x in r.json() if x["is_default"]]
            check("exactly one default", len(defaults) == 1, str(r.json()))

            r = await c.patch(f"/api/cellars/{main_id}", params={"account_id": OTHER}, json={"name": "Hijack"})
            check("cross-account patch 404", r.status_code == 404, r.text)

            print("\n== bottles ==")
            def wine(**kw):
                base = dict(producer="Château Test", wine_name="Grand Vin", vintage=2016,
                            varietals=["Cabernet Sauvignon", "Merlot"], wine_type="red",
                            country="France", region="Bordeaux", appellation="Pauillac",
                            drink_from=2024, drink_to=2040)
                base.update(kw); return base

            r = await c.post("/api/bottles", json={"account_id": ACC, "cellar_id": main_id, "wine": wine(),
                                                   "quantity": 6, "bin": "A1", "purchase_price": 95.0,
                                                   "purchase_date": "2020-03-01", "currency": "usd"})
            check("add bottle 201", r.status_code == 201, r.text)
            b1 = r.json()
            check("currency upcased", b1["currency"] == "USD", r.text)
            check("wine display name", b1["wine"]["display_name"] == "2016 Château Test Grand Vin", r.text)
            check("drink window ready", b1["wine"]["drink_window"] == "ready", r.text)
            wine_id = b1["wine"]["id"]

            # same wine + same bin => dedupe onto the same lot
            r = await c.post("/api/bottles", json={"account_id": ACC, "cellar_id": main_id, "wine": wine(),
                                                   "quantity": 3, "bin": "A1"})
            check("re-add dedupes lot", r.json()["id"] == b1["id"] and r.json()["quantity"] == 9, r.text)

            # accent/punctuation folding should hit the same wines row
            r = await c.post("/api/bottles", json={"account_id": ACC, "cellar_id": office_id,
                                                   "wine": wine(producer="Chateau Test!"), "quantity": 2, "bin": "B2"})
            check("normalized producer dedupes wine", r.json()["wine"]["id"] == wine_id, r.text)

            for w, qty, price, bin_ in [
                (wine(producer="Domaine Blanc", wine_name="Les Pierres", vintage=2021,
                      varietals=["Chardonnay"], wine_type="white", region="Burgundy",
                      appellation="Chablis", drink_from=2023, drink_to=2028), 12, 42.0, "C1"),
                (wine(producer="Bodega Sur", wine_name="Reserva", vintage=2010,
                      varietals=["Tempranillo"], wine_type="red", country="Spain",
                      region="Rioja", appellation="Rioja", drink_from=2015, drink_to=2022), 4, 28.5, "C2"),
                (wine(producer="Old Stock", wine_name="Ancient", vintage=1998,
                      varietals=["Nebbiolo"], country="Italy", region="Piedmont",
                      drink_from=None, drink_to=None), 1, 300.0, None),
            ]:
                r = await c.post("/api/bottles", json={"account_id": ACC, "cellar_id": main_id,
                                                        "wine": w, "quantity": qty, "purchase_price": price, "bin": bin_})
                assert r.status_code == 201, r.text

            print("\n== search / sort / filter ==")
            r = await c.get("/api/bottles", params={"account_id": ACC})
            check("search all cellars", r.json()["total"] == 5, r.text[:300])

            r = await c.get("/api/bottles", params={"account_id": ACC, "cellar_id": main_id})
            check("filter by cellar", r.json()["total"] == 4, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "q": "chablis"})
            check("free-text region search", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "q": "nebbiolo"})
            check("free-text varietal search", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "varietal": "chardonnay"})
            check("varietal filter case-insensitive", r.json()["total"] == 1, r.text[:200])

            # 3 lots, not 3 wines: the 2016 sits in both cellars, plus the 2010.
            r = await c.get("/api/bottles", params={"account_id": ACC, "vintage_min": 2010, "vintage_max": 2016})
            check("vintage range filter", r.json()["total"] == 3, r.text[:200])
            r = await c.get("/api/bottles", params={"account_id": ACC, "vintage_min": 2010, "vintage_max": 2016, "cellar_id": main_id})
            check("vintage range within one cellar", r.json()["total"] == 2, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "country": "spain"})
            check("country filter", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "wine_type": "white"})
            check("wine_type filter", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "drink_window": "past"})
            check("drink_window past", r.json()["total"] == 1 and r.json()["bottles"][0]["wine"]["producer"] == "Bodega Sur", r.text[:300])

            r = await c.get("/api/bottles", params={"account_id": ACC, "drink_window": "unknown"})
            check("drink_window unknown", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "min_price": 50, "max_price": 200})
            check("price range filter", r.json()["total"] == 1, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "sort": "vintage", "order": "asc"})
            vintages = [b["wine"]["vintage"] for b in r.json()["bottles"]]
            check("sort by vintage asc", vintages == sorted(vintages), str(vintages))

            r = await c.get("/api/bottles", params={"account_id": ACC, "sort": "producer", "order": "asc"})
            producers = [b["wine"]["producer"] for b in r.json()["bottles"]]
            check("sort by producer asc", producers == sorted(producers, key=str.lower), str(producers))

            r = await c.get("/api/bottles", params={"account_id": ACC, "sort": "price", "order": "desc"})
            prices = [b["purchase_price"] for b in r.json()["bottles"] if b["purchase_price"] is not None]
            check("sort by price desc, nulls last", prices == sorted(prices, reverse=True), str(prices))

            r = await c.get("/api/bottles", params={"account_id": ACC, "sort": "bogus"})
            check("bad sort 400", r.status_code == 400, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "vintage_min": 2020, "vintage_max": 2010})
            check("inverted vintage range 400", r.status_code == 400, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": ACC, "limit": 2, "offset": 0})
            check("pagination total independent of limit", r.json()["total"] == 5 and len(r.json()["bottles"]) == 2, r.text[:200])

            r = await c.get("/api/bottles", params={"account_id": OTHER})
            check("other account sees no bottles", r.json()["total"] == 0, r.text[:200])

            # SQL-injection-shaped input must be treated as a literal
            r = await c.get("/api/bottles", params={"account_id": ACC, "q": "'; DROP TABLE cellar_bottles; --"})
            check("injection string is literal", r.status_code == 200 and r.json()["total"] == 0, r.text[:200])

            print("\n== facets ==")
            r = await c.get("/api/bottles/facets", params={"account_id": ACC})
            f = r.json()
            check("facet varietals", {v["key"] for v in f["varietals"]} >= {"Cabernet Sauvignon", "Chardonnay", "Tempranillo", "Nebbiolo"}, str(f["varietals"]))
            check("facet countries", {v["key"] for v in f["countries"]} == {"France", "Spain", "Italy"}, str(f["countries"]))
            check("facet vintages desc", [v["key"] for v in f["vintages"]] == sorted([v["key"] for v in f["vintages"]], reverse=True), str(f["vintages"]))
            check("facet varietal count sums quantity", next(v["bottles"] for v in f["varietals"] if v["key"] == "Cabernet Sauvignon") == 11, str(f["varietals"]))
            check("facets expose sorts", "vintage" in f["sorts"] and "drink_windows" in f, str(f.keys()))

            print("\n== consume / move / history ==")
            r = await c.post(f"/api/bottles/{b1['id']}/consume", json={"account_id": ACC, "quantity": 2, "my_rating": 94, "note": "anniversary"})
            check("consume 2", r.json()["remaining"] == 7 and r.json()["my_rating"] == 94.0, r.text[:300])

            r = await c.post(f"/api/bottles/{b1['id']}/consume", json={"account_id": ACC, "quantity": 99})
            check("over-consume 409", r.status_code == 409, r.text[:200])

            r = await c.post(f"/api/bottles/{b1['id']}/move", json={"account_id": ACC, "to_cellar_id": office_id, "quantity": 3, "bin": "Z9"})
            check("move 3 bottles", r.json()["moved"] == 3 and r.json()["remaining"] == 4, r.text[:300])

            r = await c.post(f"/api/bottles/{b1['id']}/move", json={"account_id": OTHER, "to_cellar_id": office_id})
            check("cross-account move 404", r.status_code == 404, r.text[:200])

            r = await c.get(f"/api/bottles/{b1['id']}", params={"account_id": ACC})
            detail = r.json()
            kinds = [e["event_type"] for e in detail["history"]]
            check("history records added+consumed", "added" in kinds and "consumed" in kinds, str(kinds))
            check("detail carries wine", detail["wine"]["producer"] == "Château Test", r.text[:200])

            r = await c.get(f"/api/bottles/{b1['id']}", params={"account_id": OTHER})
            check("cross-account detail 404", r.status_code == 404, r.text[:200])

            print("\n== stats ==")
            r = await c.get(f"/api/cellars/{main_id}/stats", params={"account_id": ACC})
            s = r.json()
            check("stats bottle_count", s["bottle_count"] == 4 + 12 + 4 + 1, r.text[:400])
            check("stats capacity pct", s["capacity_used_pct"] is not None, r.text[:200])
            check("stats by_drink_window", {b["key"] for b in s["by_drink_window"]} & {"past", "unknown", "ready"}, r.text[:300])
            check("stats consumed_last_year", s["consumed_last_year"] == 2, r.text[:300])
            check("stats total_cost is a number", isinstance(s["total_cost"], (int, float)), r.text[:300])

            print("\n== label scan validation ==")
            r = await c.post("/api/labels/identify", json={"image_base64": "not!!base64!!" * 4})
            check("bad base64 400", r.status_code == 400, r.text[:200])
            r = await c.post("/api/labels/identify", json={"image_base64": "aGVsbG8gd29ybGQ" + "A" * 40, "media_type": "image/tiff"})
            check("unsupported media type 415", r.status_code == 415, r.text[:200])

            print("\n== wine intel (no API key -> clean 502, not a crash) ==")
            r = await c.get(f"/api/wines/{wine_id}/scores")
            check("scores endpoint responds", r.status_code == 200, r.text[:300])
            check("scores disclaimer present", r.json()["disclaimer"] is not None, r.text[:300])
            r = await c.get("/api/wines/99999/scores")
            check("unknown wine 404", r.status_code == 404, r.text[:200])
            r = await c.post("/api/recommendations", json={"account_id": OTHER})
            check("recommendations with empty cellar 400", r.status_code == 400, r.text[:200])

            print("\n== delete ==")
            r = await c.delete(f"/api/bottles/{b1['id']}", params={"account_id": OTHER})
            check("cross-account delete 404", r.status_code == 404, r.text[:200])
            r = await c.delete(f"/api/bottles/{b1['id']}", params={"account_id": ACC})
            check("delete bottle 204", r.status_code == 204, r.text[:200])
            r = await c.delete(f"/api/cellars/{office_id}", params={"account_id": ACC})
            check("delete cellar 204", r.status_code == 204, r.text[:200])
            r = await c.get("/api/cellars", params={"account_id": ACC})
            check("cellar gone", len(r.json()) == 1, r.text[:200])

            for cellar in r.json():
                await c.delete(f"/api/cellars/{cellar['id']}", params={"account_id": ACC})
            r = await c.get("/api/cellars", params={"account_id": ACC})
            check("cleaned up after itself", r.json() == [], r.text[:200])

    print(f"\n{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES: ' + ', '.join(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
