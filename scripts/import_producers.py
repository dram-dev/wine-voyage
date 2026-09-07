"""Fold an external producer list into the autofill reference.

The reference is curated by hand, which is fine until you have a real list —
a merchant's past-offers archive, a cellar export, a spreadsheet. This turns
such a list into reference entries without retyping it.

It accepts whatever you can actually get hold of:

    Shopify JSON     the shape /collections/<name>/products.json returns;
                     `vendor` is the producer. Merchants running Shopify
                     (Last Bottle among them) expose this without auth.
    JSON array       [{"producer": "...", "appellation": "..."}, ...]
                     or a bare ["Producer A", "Producer B"]
    CSV              a `producer` column, optionally `appellation`/`region`
    Plain text       one producer per line
    HTML             any page; text is stripped and each line treated as above

What it does NOT do is guess where an unknown producer is from. A wrong
appellation is worse than no entry, because it silently fills a user's cellar
record with a plausible lie. Unplaced names are written to a review file for you
to place, and only placed ones become entries.

    # 1. get the data (on a machine that can reach the site)
    curl -s 'https://lastbottlewines.com/collections/past/products.json?limit=250&page=1' > past-1.json

    # 2. see what is new, without writing anything
    python -m scripts.import_producers past-*.json --dry-run

    # 3. write the additions, then place whatever needs placing
    python -m scripts.import_producers past-*.json
    #    -> data/producer_additions.json   (placed, picked up by the build)
    #    -> data/producer_review.txt       (unplaced, for you to fill in)

    # 4. rebuild
    python -m scripts.build_reference
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from scripts.build_reference import APPELLATIONS, ALIASES, PRODUCERS, load_repo_producers, normalize
from scripts.reference_california import CALIFORNIA_AVAS, CALIFORNIA_PRODUCERS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ADDITIONS = DATA / "producer_additions.json"
REVIEW = DATA / "producer_review.txt"

# Lines that are plainly not a producer name.
NOISE_LINE = re.compile(
    r"^\s*(?:\$|\d|add to cart|sold out|shop|home|menu|sign in|cart|search|"
    r"free shipping|view all|load more|previous|next)\b",
    re.IGNORECASE,
)

# Punctuation no winery name carries — usually a fragment of markup or of a
# malformed file that fell through to the text handling.
NOT_A_NAME = re.compile(r"[{}<>|\\=]|https?://")

# A trailing price that survived tag-stripping.
TRAILING_PRICE = re.compile(r"\s*\$\s*[\d,]+(?:\.\d{2})?\s*$")

# "2021 Arista Russian River Pinot Noir" is a product title, not a producer.
# Guessing the producer out of one is how a cellar record gets a plausible lie
# in it, so these are reported and skipped rather than imported.
LOOKS_LIKE_TITLE = re.compile(r"^\s*(?:19|20)\d{2}\b")


# Product titles encountered while parsing, reported so a source of the wrong
# shape is obvious rather than silently half-imported.
TITLES_SEEN: list[str] = []


class _TextExtractor(HTMLParser):
    """Strip tags, keeping one line of text per block element."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        else:
            # A newline on *every* tag, not just block-level ones: a price in a
            # nested <span> would otherwise be glued onto the name beside it.
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def known_appellations() -> dict[str, str]:
    """Normalized appellation/region name -> canonical name."""
    table: dict[str, str] = {}
    for name, region, *_ in APPELLATIONS + CALIFORNIA_AVAS:
        table[normalize(name)] = name
        table.setdefault(normalize(region), name)
    for alias, canonical in ALIASES.items():
        table.setdefault(normalize(alias), canonical)
    return table


def known_producers() -> set[str]:
    pairs = PRODUCERS + CALIFORNIA_PRODUCERS + load_repo_producers()
    existing = {normalize(name) for name, _ in pairs}
    if ADDITIONS.exists():
        for row in json.loads(ADDITIONS.read_text()):
            existing.add(normalize(row["producer"]))
    return existing


def parse(path: Path) -> list[tuple[str, str | None]]:
    """Extract (producer, appellation-or-None) pairs from one file."""
    raw = path.read_text(errors="replace")
    suffix = path.suffix.lower()

    if suffix == ".json" or raw.lstrip()[:1] in "[{":
        try:
            return _from_json(json.loads(raw))
        except (ValueError, KeyError):
            pass  # fall through to the text handling below
    if suffix == ".csv":
        return _from_csv(raw)
    if suffix in (".html", ".htm") or "<html" in raw[:2000].lower():
        parser = _TextExtractor()
        parser.feed(raw)
        raw = parser.text()
    return [(line, None) for line in _clean_lines(raw)]


def _from_json(payload) -> list[tuple[str, str | None]]:
    # Shopify: {"products": [{"vendor": "...", ...}, ...]}
    if isinstance(payload, dict) and isinstance(payload.get("products"), list):
        return [(p["vendor"], None) for p in payload["products"] if p.get("vendor")]
    if isinstance(payload, list):
        out: list[tuple[str, str | None]] = []
        for entry in payload:
            if isinstance(entry, str):
                out.append((entry, None))
            elif isinstance(entry, dict):
                name = entry.get("producer") or entry.get("vendor") or entry.get("winery")
                if name:
                    out.append((name, entry.get("appellation") or entry.get("region")))
        return out
    raise ValueError("unrecognized JSON shape")


def _from_csv(raw: str) -> list[tuple[str, str | None]]:
    rows = list(csv.DictReader(raw.splitlines()))
    out = []
    for row in rows:
        lowered = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        name = lowered.get("producer") or lowered.get("vendor") or lowered.get("winery")
        if name:
            out.append((name, lowered.get("appellation") or lowered.get("region") or None))
    return out


def _clean_lines(raw: str) -> list[str]:
    seen, out = set(), []
    for line in raw.splitlines():
        line = TRAILING_PRICE.sub("", " ".join(line.split()))
        if len(line) < 3 or len(line) > 80 or NOISE_LINE.match(line):
            continue
        if NOT_A_NAME.search(line):
            continue
        if LOOKS_LIKE_TITLE.match(line):
            TITLES_SEEN.append(line)
            continue
        key = normalize(line)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    parser.add_argument("--default-appellation", metavar="NAME",
                        help="Place every unplaced producer here (use only if the "
                             "source really is one region)")
    args = parser.parse_args()

    appellations = known_appellations()
    existing = known_producers()
    if args.default_appellation and normalize(args.default_appellation) not in appellations:
        print(f"unknown appellation: {args.default_appellation!r}")
        return 1

    placed: dict[str, dict] = {}
    unplaced: dict[str, str] = {}
    seen_new: set[str] = set()
    total = 0

    for path in args.files:
        if not path.exists():
            print(f"missing file: {path}")
            return 1
        for name, place in parse(path):
            total += 1
            name = name.strip()
            key = normalize(name)
            if not key or key in existing or key in seen_new:
                continue
            seen_new.add(key)
            canonical = appellations.get(normalize(place)) if place else None
            if canonical is None and args.default_appellation:
                canonical = appellations[normalize(args.default_appellation)]
            if canonical:
                placed[key] = {"producer": name, "appellation": canonical}
            else:
                unplaced[key] = name

    if TITLES_SEEN:
        print(f"skipped {len(TITLES_SEEN)} line(s) that look like product titles "
              f"rather than producer names, e.g. {TITLES_SEEN[0]!r}.")
        print("  A Shopify products.json has a `vendor` field that is the producer "
              "— prefer that over a scraped page.\n")

    print(f"read {total} rows from {len(args.files)} file(s)")
    print(f"  already in the reference: {total - len(seen_new)}")
    print(f"  new, placed:              {len(placed)}")
    print(f"  new, need an appellation: {len(unplaced)}")

    if args.dry_run:
        for row in list(placed.values())[:10]:
            print(f"    + {row['producer']}  ->  {row['appellation']}")
        for name in list(unplaced.values())[:10]:
            print(f"    ? {name}")
        if len(placed) + len(unplaced) > 20:
            print("    …")
        return 0

    if placed:
        merged = json.loads(ADDITIONS.read_text()) if ADDITIONS.exists() else []
        merged.extend(placed.values())
        merged.sort(key=lambda row: normalize(row["producer"]))
        ADDITIONS.write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(placed)} to {ADDITIONS.relative_to(ROOT)} "
              f"({len(merged)} total) — rerun scripts.build_reference to pick them up")
    if unplaced:
        REVIEW.write_text(
            "# Producers with no appellation. Put one after a tab or comma and\n"
            "# re-run: python -m scripts.import_producers data/producer_review.txt\n"
            + "\n".join(sorted(unplaced.values())) + "\n"
        )
        print(f"wrote {len(unplaced)} to {REVIEW.relative_to(ROOT)} for placement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
