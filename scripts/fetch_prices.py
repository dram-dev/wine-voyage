"""Price the cellar from retailer feeds that are public by design.

Wine-Searcher and Vivino are the obvious sources and neither is open: no free
public API, and terms that forbid scraping. What *is* public, deliberately and
without a key, are the storefront product feeds that e-commerce platforms serve
to their own shop pages:

    Shopify        https://<store>/products.json?limit=250&page=N
                   also /collections/<name>/products.json
    WooCommerce    https://<store>/wp-json/wc/store/v1/products?per_page=100&page=N

Both are documented, unauthenticated endpoints meant to be read by clients. A
great many independent wine merchants run one or the other. Prices are real,
current, and per-format.

    python -m scripts.fetch_prices https://example-wines.com
    python -m scripts.fetch_prices saved-feed.json --dry-run
    python -m scripts.fetch_prices https://example-wines.com --write

Nothing is written unless --write is passed, and then only for wines already in
the database — the point is to value the bottles someone actually holds, not to
accumulate prices for wines nobody owns. Each price is stored as `market` with
the shop's hostname as its source and the time it was read, so the value tracker
can rank it against a hand-entered price and age it out.

Be a good citizen: this paginates with a delay and identifies itself. Check a
shop's robots.txt and terms before pointing it at them; "publicly reachable" and
"yours to bulk-collect" are not the same thing, and one polite pass a week is a
very different proposition from a scraper.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import asyncpg

from server.config import settings
from server.wine_identity import natural_key, normalize
from server.wine_titles import parse_title

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "price_observations.json"

USER_AGENT = "wine-voyage/0.1 (personal cellar tool; +https://github.com/dram-dev/wine-voyage)"
SHOPIFY_PATH = "/products.json"
WOO_PATH = "/wp-json/wc/store/v1/products"
DEFAULT_SIZE = 750
MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def money(value) -> Optional[float]:
    """A price from whatever the feed calls one. WooCommerce sends minor units."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = MONEY.search(str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def fetch(url: str, timeout: int = 30) -> Optional[dict | list]:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
        print(f"  ! {url}: {exc}", file=sys.stderr)
        return None


def shopify_products(payload) -> Iterable[dict]:
    """Shopify: one row per variant, because size and price live there."""
    for product in (payload or {}).get("products", []):
        vendor = product.get("vendor")
        title = product.get("title")
        handle = product.get("handle")
        for variant in product.get("variants") or [{}]:
            price = money(variant.get("price"))
            if not title or price is None:
                continue
            yield {
                "title": " ".join(x for x in (title, variant.get("title")) if x and x != "Default Title"),
                "vendor": vendor,
                "price": price,
                "available": bool(variant.get("available", True)),
                "handle": handle,
            }


def woo_products(payload) -> Iterable[dict]:
    """WooCommerce Store API: prices are minor units, with the divisor given."""
    for product in payload or []:
        prices = product.get("prices") or {}
        minor = money(prices.get("price"))
        if minor is None:
            continue
        divisor = 10 ** int(prices.get("currency_minor_unit", 2) or 0)
        title = product.get("name")
        if not title:
            continue
        yield {
            "title": title,
            "vendor": None,
            "price": minor / divisor,
            "available": product.get("is_in_stock", True),
            "handle": product.get("slug"),
            "currency": prices.get("currency_code"),
        }


def read_file(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except ValueError:
            print(f"  ! {path.name} is not valid JSON", file=sys.stderr)
            return []
        if isinstance(payload, dict) and "products" in payload:
            return list(shopify_products(payload))
        if isinstance(payload, list):
            return list(woo_products(payload))
        return []
    rows = []
    for row in csv.DictReader(text.splitlines()):
        keys = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        title = keys.get("title") or keys.get("name") or keys.get("wine")
        price = money(keys.get("price"))
        if title and price is not None:
            rows.append({"title": title, "vendor": keys.get("producer") or keys.get("vendor"),
                         "price": price, "available": True, "handle": None})
    return rows


def crawl(base: str, pages: int, delay: float) -> list[dict]:
    """Try Shopify, then WooCommerce. A shop is one or the other, not both."""
    base = base.rstrip("/")
    rows: list[dict] = []

    for page in range(1, pages + 1):
        payload = fetch(f"{base}{SHOPIFY_PATH}?limit=250&page={page}")
        batch = list(shopify_products(payload)) if isinstance(payload, dict) else []
        if not batch:
            break
        rows.extend(batch)
        print(f"  shopify page {page}: {len(batch)} variants")
        _sleep(delay)
    if rows:
        return rows

    for page in range(1, pages + 1):
        payload = fetch(f"{base}{WOO_PATH}?per_page=100&page={page}")
        batch = list(woo_products(payload)) if isinstance(payload, list) else []
        if not batch:
            break
        rows.extend(batch)
        print(f"  woocommerce page {page}: {len(batch)} products")
        _sleep(delay)

    if not rows:
        print(f"  ! {base} serves neither a Shopify nor a WooCommerce product feed", file=sys.stderr)
    return rows


def _sleep(seconds: float) -> None:
    if seconds > 0:
        import time
        time.sleep(seconds)


def observe(rows: Iterable[dict], source: str, all_sizes: bool) -> tuple[list[dict], list[str]]:
    """Turn shop listings into per-wine price observations."""
    grouped: dict[tuple, list[float]] = defaultdict(list)
    meta: dict[tuple, dict] = {}
    unmatched: list[str] = []

    for row in rows:
        parsed = parse_title(row["title"], row.get("vendor"))
        if not parsed["producer"]:
            unmatched.append(row["title"])
            continue
        size = parsed["bottle_size_ml"] or DEFAULT_SIZE
        if size != DEFAULT_SIZE and not all_sizes:
            continue
        key = (parsed["producer"], normalize(parsed["wine_name"]), parsed["vintage"], size)
        grouped[key].append(row["price"])
        meta.setdefault(key, {
            "producer": parsed["producer"], "wine_name": parsed["wine_name"],
            "vintage": parsed["vintage"], "bottle_size_ml": size,
        })

    observations = []
    for key, prices in grouped.items():
        prices.sort()
        mid = prices[len(prices) // 2] if len(prices) % 2 else (
            (prices[len(prices) // 2 - 1] + prices[len(prices) // 2]) / 2)
        observations.append({
            **meta[key],
            "low": prices[0], "mid": round(mid, 2), "high": prices[-1],
            "observations": len(prices), "source": source,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    observations.sort(key=lambda o: (o["producer"], o["wine_name"] or "", o["vintage"] or 0))
    return observations, unmatched


async def write_valuations(observations: list[dict], currency: str) -> tuple[int, int]:
    """Store prices for wines the database already has. Nothing else."""
    from server.valuation import store_valuations

    conn = await asyncpg.connect(settings.database_url)
    matched = skipped = 0
    try:
        for row in observations:
            key = natural_key(row["producer"], row["wine_name"], row["vintage"], row["bottle_size_ml"])
            wine_id = await conn.fetchval("SELECT id FROM wines WHERE natural_key = $1", key)
            if wine_id is None:
                skipped += 1
                continue
            await store_valuations(conn, wine_id, [{
                "source": row["source"], "source_kind": "market",
                "low": row["low"], "mid": row["mid"], "high": row["high"],
                "currency": currency,
                "note": f"{row['observations']} listing(s)",
                "confidence": None,
            }])
            matched += 1
    finally:
        await conn.close()
    return matched, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", help="shop URLs, or saved feed files")
    parser.add_argument("--write", action="store_true",
                        help="store prices for wines already in the database")
    parser.add_argument("--dry-run", action="store_true", help="parse and report, write nothing")
    parser.add_argument("--pages", type=int, default=8, help="pages per shop (default 8)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--all-sizes", action="store_true",
                        help="keep formats other than 750ml (they are priced differently)")
    parser.add_argument("--limit", type=int, default=20, help="rows to print")
    args = parser.parse_args()

    rows: list[dict] = []
    source_names: list[str] = []
    for source in args.sources:
        path = Path(source)
        if path.exists():
            print(f"Reading {path.name}")
            rows.extend(read_file(path))
            source_names.append(path.stem)
        elif source.startswith(("http://", "https://")):
            host = urllib.parse.urlsplit(source).hostname or source
            print(f"Fetching {host}")
            rows.extend(crawl(source, args.pages, args.delay))
            source_names.append(host)
        else:
            print(f"  ! not a file or a URL: {source}", file=sys.stderr)

    if not rows:
        print("Nothing to price.", file=sys.stderr)
        return 1

    observations, unmatched = observe(rows, ", ".join(sorted(set(source_names))), args.all_sizes)
    print(f"\n{len(rows)} listings -> {len(observations)} wines priced, "
          f"{len(unmatched)} titles unresolved")

    for row in observations[:args.limit]:
        name = " ".join(x for x in (str(row["vintage"] or "NV"), row["producer"], row["wine_name"] or "") if x)
        spread = f"{row['low']:.0f}" if row["low"] == row["high"] else f"{row['low']:.0f}-{row['high']:.0f}"
        print(f"  {name[:52]:54} {spread:>12}  ({row['observations']})")
    if len(observations) > args.limit:
        print(f"  … and {len(observations) - args.limit} more")

    if unmatched:
        print(f"\nUnresolved titles ({len(unmatched)}) — the producer is not in the reference, "
              f"or the title does not lead with it:")
        for title in unmatched[:8]:
            print(f"  {title[:80]}")
        if len(unmatched) > 8:
            print(f"  … and {len(unmatched) - 8} more")

    OUT.write_text(json.dumps(observations, indent=1, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}")

    if args.write and not args.dry_run:
        matched, skipped = asyncio.run(write_valuations(observations, args.currency))
        print(f"stored {matched} market valuations; "
              f"{skipped} priced wines are not in your cellar and were skipped")
    elif args.write:
        print("(--dry-run given, so nothing was stored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
