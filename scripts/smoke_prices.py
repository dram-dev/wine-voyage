"""Smoke test for the public-feed price path.

Covers the part that can silently attach a price to the wrong wine: reading a
shop's product title as a producer, a vintage, a cuvée and a size, and
aggregating listings across shops into one observation per wine.

    DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_prices

Exits non-zero if any check fails.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from scripts.fetch_prices import money, observe, read_file, shopify_products, woo_products
from server.wine_titles import bottle_size_ml, parse_title

fails: list[str] = []


def check(label, cond, detail=""):
    print(("  PASS " if cond else "  FAIL ") + label + ("" if cond else f"  <- {detail}"))
    if not cond:
        fails.append(label)


def main() -> int:
    print("== a shop title reads as a wine ==")
    r = parse_title("2021 Denner Vineyards Ditch Digger Paso Robles 750ml")
    check("producer", r["producer"] == "Denner", str(r["producer"]))
    check("vintage", r["vintage"] == 2021, str(r["vintage"]))
    check("cuvée, without the producer or the place", r["wine_name"] == "Ditch Digger", str(r["wine_name"]))
    check("size", r["bottle_size_ml"] == 750, str(r["bottle_size_ml"]))

    r = parse_title("Denner The Dirt Worshipper 2021", vendor="Denner Vineyards")
    check("a vendor field does not double the producer into the cuvée",
          r["producer"] == "Denner" and r["wine_name"] == "The Dirt Worshipper", str(r))

    r = parse_title("2019 Ridge Lytton Springs 1.5L")
    check("a producer entry that is really a wine still yields both",
          r["wine_name"] == "Lytton Springs", str(r["wine_name"]))
    check("magnum recognised", r["bottle_size_ml"] == 1500, str(r["bottle_size_ml"]))

    check("named formats", bottle_size_ml("Krug Grande Cuvee Magnum") == 1500)
    check("half bottles", bottle_size_ml("Sauternes half bottle") == 375)
    check("no size claimed is not a size", bottle_size_ml("2018 Insignia") is None)

    r = parse_title("Assorted Wine Tote Bag")
    check("a non-wine yields no producer rather than a guess", r["producer"] is None, str(r))

    r = parse_title("Krug Grande Cuvee NV Champagne")
    check("NV is recorded, not silently a missing vintage",
          r["vintage"] is None and r["non_vintage"], str(r))

    print("\n== feeds parse ==")
    shopify = {"products": [{"title": "2018 Joseph Phelps Insignia", "vendor": "Joseph Phelps Vineyards",
                             "handle": "i", "variants": [{"title": "750ml", "price": "289.99", "available": True},
                                                         {"title": "1.5L", "price": "620.00", "available": True}]}]}
    rows = list(shopify_products(shopify))
    check("shopify yields one row per variant", len(rows) == 2, str(len(rows)))
    check("shopify price is a number", rows[0]["price"] == 289.99, str(rows[0]["price"]))

    woo = [{"name": "2018 Joseph Phelps Insignia", "slug": "i", "is_in_stock": True,
            "prices": {"price": "31500", "currency_code": "USD", "currency_minor_unit": 2}}]
    rows = list(woo_products(woo))
    check("woocommerce minor units are divided", rows[0]["price"] == 315.0, str(rows[0]["price"]))
    check("money parses a formatted string", money("$1,234.50") == 1234.50, str(money("$1,234.50")))

    print("\n== observations ==")
    listings = [
        {"title": "2018 Joseph Phelps Insignia", "vendor": None, "price": 290.0, "available": True},
        {"title": "2018 Joseph Phelps Vineyards Insignia Napa Valley", "vendor": None, "price": 315.0, "available": True},
        {"title": "2018 Joseph Phelps Insignia 1.5L", "vendor": None, "price": 620.0, "available": True},
        {"title": "Assorted Tote Bag", "vendor": None, "price": 12.0, "available": True},
    ]
    obs, unmatched = observe(listings, "test", all_sizes=False)
    check("one wine, not three", len(obs) == 1, str([(o["producer"], o["wine_name"]) for o in obs]))
    check("two shops' prices are one spread", (obs[0]["low"], obs[0]["high"]) == (290.0, 315.0), str(obs[0]))
    check("mid is the median", obs[0]["mid"] == 302.5, str(obs[0]["mid"]))
    check("the magnum is not mixed into a 750 price", obs[0]["observations"] == 2, str(obs[0]["observations"]))
    check("the tote bag is reported, not priced", unmatched == ["Assorted Tote Bag"], str(unmatched))

    obs_all, _ = observe(listings, "test", all_sizes=True)
    check("--all-sizes keeps formats apart", len(obs_all) == 2, str(len(obs_all)))

    print("\n== files ==")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "feed.json"
        path.write_text(json.dumps(shopify))
        check("a saved shopify feed reads back", len(read_file(path)) == 2)
        bad = Path(tmp) / "bad.json"
        bad.write_text("{ not json")
        check("malformed json is survivable", read_file(bad) == [])
        empty = Path(tmp) / "empty.csv"
        empty.write_text("")
        check("an empty file is survivable", read_file(empty) == [])

    print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES: " + ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
