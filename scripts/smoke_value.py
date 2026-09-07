"""Smoke test for the value tracker: totals, history, movers, manual prices.

Runs the real app in-process against a real Postgres. The pricing call is
stubbed with a deterministic fake, so this costs nothing and does not need an
Anthropic key — what is under test is the accounting, not the model.

    pip install httpx
    DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_value

Exits non-zero if any check fails.
"""
import asyncio
import os
import sys
import uuid

os.environ.setdefault("ANTHROPIC_API_KEY", "smoke-test-no-key")

import httpx

import server.routes.wine_intel as wi
from server.main import app

# `wines` dedupes on producer+cuvee+vintage+size, so the producers must be
# unique per run or a rerun would inherit the previous run's prices.
RUN = uuid.uuid4().hex[:8]
ACC = f"val-{RUN}"
OTHER = f"val-{RUN}-b"
fails = []
def check(l,c,d=""):
    print(("  PASS " if c else "  FAIL ")+l+("" if c else f"  <- {d}")); 
    if not c: fails.append(l)

# Stand in for the pricing provider with a fixed price per producer.
PRICES: dict[str, float] = {}


async def fake_fetch_valuations(wine):
    mid = PRICES.get(wine["producer"])
    if mid is None:
        return []
    return [{
        "source": "Stub market", "source_kind": "market",
        "low": mid * 0.8, "mid": mid, "high": mid * 1.3,
        "currency": "USD", "note": "stub", "confidence": 0.9,
    }]

async def main():
    wi.fetch_valuations = fake_fetch_valuations
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with app.router.lifespan_context(app):
            cell = (await c.post("/api/cellars", json={"account_id":ACC,"name":f"Vault {RUN}","capacity":100})).json()
            cid = cell["id"]
            spec=[(f"Alpha Estate {RUN}",2015,100.0,3,300.0),   # cost 100 -> value 300 (gain)
                  (f"Beta Domaine {RUN}",2018,80.0,2,40.0),     # cost 80 -> value 40  (loss)
                  (f"Gamma Cellars {RUN}",2020,50.0,6,55.0),    # small gain
                  (f"Delta Vines {RUN}",2019,None,4,90.0)]      # no cost recorded
            ids=[]
            for producer,vintage,cost,qty,price in spec:
                PRICES[producer]=price
                r = await c.post("/api/bottles", json={"account_id":ACC,"cellar_id":cid,"quantity":qty,
                    "purchase_price":cost,"bin":producer[:3],
                    "wine":{"producer":producer,"vintage":vintage,"varietals":["Merlot"],"region":"Test Valley","country":"Testland"}})
                assert r.status_code==201, r.text
                ids.append(r.json()["wine"]["id"])

            print("\n== before revaluation ==")
            v = (await c.get(f"/api/cellars/{cid}/value", params={"account_id":ACC})).json()
            check("no value before pricing", v["market_value"] is None, str(v["market_value"]))
            check("coverage 0%", v["coverage_pct"]==0.0, str(v["coverage_pct"]))
            check("cost basis still computed", v["cost_basis"]==100*3+80*2+50*6, str(v["cost_basis"]))

            print("\n== bulk revaluation ==")
            r = await c.post(f"/api/cellars/{cid}/revalue", json={"account_id":ACC})
            body=r.json()
            check("revalue prices every wine", body["priced"]==4, r.text)
            check("reports cellar size", body["wines_in_cellar"]==4, r.text)

            r = await c.post(f"/api/cellars/{cid}/revalue", json={"account_id":ACC})
            check("second run skips fresh valuations", r.json()["priced"]==0, r.text)
            r = await c.post(f"/api/cellars/{cid}/revalue", json={"account_id":ACC,"force":True})
            check("force re-prices anyway", r.json()["priced"]==4, r.text)

            r = await c.post(f"/api/cellars/{cid}/revalue", json={"account_id":OTHER})
            check("cross-account revalue 404", r.status_code==404, r.text[:150])

            print("\n== total cellar value ==")
            v = (await c.get(f"/api/cellars/{cid}/value", params={"account_id":ACC})).json()
            expected_all = 300*3+40*2+55*6+90*4    # every priced lot
            expected_costed = 300*3+40*2+55*6      # lots that also have a cost
            check("market_value_all sums every lot", v["market_value_all"]==expected_all, str(v["market_value_all"]))
            check("market_value uses the costed intersection", v["market_value"]==expected_costed, str(v["market_value"]))
            check("cost_basis_priced matches", v["cost_basis_priced"]==100*3+80*2+50*6, str(v["cost_basis_priced"]))
            check("unrealized gain correct", v["unrealized_gain"]==expected_costed-(100*3+80*2+50*6), str(v["unrealized_gain"]))
            check("coverage now 100%", v["coverage_pct"]==100.0, str(v["coverage_pct"]))
            check("low/high band brackets mid", v["market_low"]<v["market_value_all"]<v["market_high"], f"{v['market_low']}/{v['market_high']}")
            check("estimated share 0 with a market source", v["estimated_share_pct"]==0.0, str(v["estimated_share_pct"]))

            print("\n== movers ==")
            gainers=[g["display_name"] for g in v["top_gainers"]]
            losers=[l["display_name"] for l in v["top_losers"]]
            check("biggest gainer is Alpha", "Alpha" in gainers[0], str(gainers))
            check("loser list contains Beta", any("Beta" in l for l in losers), str(losers))
            check("no-cost lot excluded from movers", not any("Delta" in g for g in gainers+losers), str(gainers+losers))
            alpha=v["top_gainers"][0]
            check("gain_pct correct", alpha["gain_pct"]==200.0, str(alpha["gain_pct"]))
            check("most_valuable includes the no-cost lot", any("Delta" in m["display_name"] for m in v["most_valuable"]), str([m["display_name"] for m in v["most_valuable"]]))
            check("by_region groups", v["by_region"][0]["key"]=="Test Valley", str(v["by_region"]))

            print("\n== history ==")
            check("snapshot written on read", len(v["history"])>=1, str(v["history"]))
            check("snapshot carries market value", v["history"][-1]["market_value"]==expected_costed, str(v["history"][-1]))
            v2 = (await c.get(f"/api/cellars/{cid}/value", params={"account_id":ACC})).json()
            check("same-day read does not duplicate the point", len(v2["history"])==len(v["history"]), str(len(v2["history"])))

            h = (await c.get(f"/api/wines/{ids[0]}/valuation/history")).json()
            check("per-wine history accumulated", len(h["points"])>=2, str(len(h["points"])))
            check("history points carry source", h["points"][0]["source"]=="Stub market", str(h["points"][0]))

            print("\n== manual override ==")
            r = await c.put(f"/api/wines/{ids[0]}/valuation", json={"account_id":ACC,"mid":500,"low":450,"high":600})
            check("manual valuation accepted", r.status_code==200, r.text[:200])
            check("manual ranks first", r.json()["valuations"][0]["source_kind"]=="manual", r.text[:250])

            r = await c.put(f"/api/wines/{ids[0]}/valuation", json={"account_id":OTHER,"mid":1})
            check("manual override 403 for a wine you don't hold", r.status_code==403, r.text[:150])
            r = await c.put(f"/api/wines/{ids[0]}/valuation", json={"account_id":ACC,"mid":100,"low":200})
            check("low>mid rejected", r.status_code==422, r.text[:150])

            v3 = (await c.get(f"/api/cellars/{cid}/value", params={"account_id":ACC})).json()
            check("manual price flows into the total", v3["market_value"]==500*3+40*2+55*6, str(v3["market_value"]))

            print("\n== it reaches the rest of the app ==")
            s = (await c.get(f"/api/cellars/{cid}/stats", params={"account_id":ACC})).json()
            check("dashboard stats now show a value", s["market_value"] is not None and s["market_value"]>0, str(s["market_value"]))
            b = (await c.get("/api/bottles", params={"account_id":ACC,"sort":"value","order":"desc"})).json()
            check("bottles sort by value", b["bottles"][0]["wine"]["producer"]==f"Alpha Estate {RUN}", str([x["wine"]["producer"] for x in b["bottles"]]))
            check("bottle carries lot_value", b["bottles"][0]["lot_value"]==1500.0, str(b["bottles"][0].get("lot_value")))

            r = await c.get(f"/api/cellars/{cid}/value", params={"account_id":OTHER})
            check("cross-account value 404", r.status_code==404, r.text[:150])

            await c.delete(f"/api/cellars/{cid}", params={"account_id":ACC})
            r = await c.get("/api/cellars", params={"account_id":ACC})
            check("cleaned up after itself", r.json()==[], r.text[:150])
            print("\n"+("ALL PASS" if not fails else f"{len(fails)} FAILURES: "+", ".join(fails)))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
