"""Reconcile the cuvée database against a list of rated wines.

The reference maps a producer to an appellation, which is enough to fill a
form's place fields but not enough to say what is in the bottle: a producer's
range spans grapes and styles the appellation cannot predict. `BOTTLINGS` in
scripts/build_reference.py closes that for a handful of producers by hand. This
says how far that hand-curation actually reaches, against a list of wines
someone else thought worth rating.

    python -m scripts.reconcile_cuvees                    # against the repo's own lists
    python -m scripts.reconcile_cuvees critics.csv        # against a supplied list
    python -m scripts.reconcile_cuvees --emit             # write what is missing

Accepted list formats, because a critic list arrives in whatever shape you can
get it out in:

    CSV/TSV     a `producer` column and a `wine`/`cuvee`/`wine_name` column
    JSON        objects with those keys, or the shape of data/top_rated*.json
    text        one "Producer — Wine" or "Producer, Wine" per line

Reporting is in four buckets, because they need different work:

    unknown producer      the reference has never heard of them
    no cuvées at all      we know where they are, nothing about what they make
    cuvée missing         we hold some of their range, not this wine
    corroborated          the list names a wine we already had

`--emit` writes the missing cuvées to data/cuvee_additions.json, which
build_reference.py folds in beside the curated table. It writes names and notes
only. It does not invent grapes: a name that states its grape is read at resolve
time, and a proprietary name that does not is better left saying nothing than
saying something plausible.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator, Optional

from server.wine_reference import find_bottling, find_producer, normalize, reference

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPO_LISTS = ("top_rated_sample.json", "top_rated_california_sample.json")
OUT = DATA / "cuvee_additions.json"

# "Grande Cuvee (Pinot-led blend)" is a name and a gloss. Keep them apart.
PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")
SPLIT_LINE = re.compile(r"\s+[—–-]\s+|\t|\s*\|\s*|,\s*")


def clean(name: str) -> tuple[str, Optional[str]]:
    """A cuvée name, and whatever was parenthesised after it."""
    text = " ".join((name or "").split())
    match = PAREN.search(text)
    if not match:
        return text, None
    return PAREN.sub("", text).strip(), match.group(1).strip() or None


def from_repo_lists() -> Iterator[tuple[str, str, Optional[str]]]:
    for filename in REPO_LISTS:
        path = DATA / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for appellation in payload.get("appellations", []):
            for winery in appellation.get("top_wineries", []):
                producer = winery.get("name")
                for entry in winery.get("top_varietals", []):
                    wine = entry.get("varietal")
                    if producer and wine:
                        yield producer, wine, entry.get("note")


def from_json(payload) -> Iterator[tuple[str, str, Optional[str]]]:
    if isinstance(payload, dict) and payload.get("appellations"):
        for appellation in payload["appellations"]:
            for winery in appellation.get("top_wineries", []):
                for entry in winery.get("top_varietals", []):
                    if winery.get("name") and entry.get("varietal"):
                        yield winery["name"], entry["varietal"], entry.get("note")
        return
    rows = payload if isinstance(payload, list) else payload.get("wines") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        producer = row.get("producer") or row.get("winery") or row.get("vendor")
        wine = row.get("wine") or row.get("cuvee") or row.get("wine_name") or row.get("name")
        if producer and wine:
            yield str(producer), str(wine), row.get("note")


def from_delimited(text: str) -> Iterator[tuple[str, str, Optional[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = None
    if dialect and csv.Sniffer().has_header(sample):
        for row in csv.DictReader(text.splitlines(), dialect=dialect):
            keys = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            producer = keys.get("producer") or keys.get("winery")
            wine = keys.get("wine") or keys.get("cuvee") or keys.get("wine_name")
            if producer and wine:
                yield producer, wine, keys.get("note") or None
        return
    # Plain lines: "Producer — Wine".
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p for p in SPLIT_LINE.split(line) if p.strip()]
        if len(parts) >= 2:
            yield parts[0].strip(), parts[1].strip(), None


def read_list(path: Path) -> Iterator[tuple[str, str, Optional[str]]]:
    text = path.read_text(errors="replace")
    if path.suffix.lower() == ".json":
        try:
            yield from from_json(json.loads(text))
            return
        except ValueError:
            print(f"  ! {path.name} is not valid JSON; reading it as text", file=sys.stderr)
    yield from from_delimited(text)


def reconcile(rows: Iterable[tuple[str, str, Optional[str]]]) -> dict:
    buckets: dict[str, list] = {"unknown": [], "no_cuvees": [], "missing": [], "corroborated": []}
    seen: set[tuple[str, str]] = set()

    for producer, raw_wine, note in rows:
        wine, gloss = clean(raw_wine)
        if not wine:
            continue
        key = (normalize(producer), normalize(wine))
        if key in seen:
            continue
        seen.add(key)

        entry, quality = find_producer(producer)
        if not entry or quality not in ("exact", "strong"):
            # A near miss is worth naming. "Marchesi Antinori" does not
            # confidently match "Antinori" — the leading word differs, and that
            # rule is what stops "Sonoma Ridge Cellars" resolving to Ridge — but
            # a human reading the report knows at a glance whether it is the
            # same house, and can add an alias.
            buckets["unknown"].append({
                "producer": producer, "wine": wine,
                "near": entry["name"] if entry else None, "quality": quality,
            })
            continue

        canonical = entry["name"]
        record = {
            "producer": canonical, "wine": wine,
            "note": (note or gloss or "").strip() or None,
            "appellation": entry.get("appellation"),
        }
        if not entry.get("bottlings"):
            buckets["no_cuvees"].append(record)
        elif find_bottling(entry, wine):
            buckets["corroborated"].append(record)
        else:
            buckets["missing"].append(record)

    return buckets


def report(buckets: dict, limit: int) -> None:
    total = sum(len(v) for v in buckets.values())
    held = len(buckets["corroborated"])
    print(f"\n{total} wines on the list, over "
          f"{len({r['producer'] for k in ('no_cuvees','missing','corroborated') for r in buckets[k]})} "
          f"producers the reference knows.\n")
    print(f"  corroborated       {held:>4}   the list names a cuvée we already hold")
    print(f"  cuvée missing      {len(buckets['missing']):>4}   we hold some of this producer's range, not this wine")
    print(f"  no cuvées at all   {len(buckets['no_cuvees']):>4}   we know where they are, nothing about what they make")
    print(f"  unknown producer   {len(buckets['unknown']):>4}   not in the reference")
    if total:
        print(f"\n  cuvée coverage     {held / total:.0%}")

    for label, key in (("Producers with no cuvées", "no_cuvees"),
                       ("Wines missing from a producer we do cover", "missing"),
                       ("Producers the reference does not know", "unknown")):
        rows = buckets[key]
        if not rows:
            continue
        print(f"\n{label} ({len(rows)}):")
        for row in rows[:limit]:
            line = f"  {row['producer']:38} {row['wine']}"
            if row.get("near"):
                line += f"   (near miss: {row['near']}, {row['quality']})"
            print(line)
        if len(rows) > limit:
            print(f"  … and {len(rows) - limit} more")

    near = [r for r in buckets["unknown"] if r.get("near")]
    if near:
        plural = "is a near miss" if len(near) == 1 else "are near misses"
        print(f"\n{len(near)} of the unknown producers {plural}. Where one is the same house "
              f"under another name,\nadd it to ALIASES in scripts/build_reference.py and re-run.")


def emit(buckets: dict) -> int:
    """Write the missing cuvées for build_reference.py to fold in.

    Names and notes only. A name that states its grape is read at resolve time;
    one that does not is left saying nothing rather than something plausible.
    """
    by_producer: dict[str, list[dict]] = {}
    for row in buckets["no_cuvees"] + buckets["missing"]:
        record = {"wine_name": row["wine"]}
        if row["note"]:
            record["note"] = row["note"][:160]
        by_producer.setdefault(row["producer"], []).append(record)

    payload = [{"producer": p, "bottlings": b} for p, b in sorted(by_producer.items())]
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    count = sum(len(p["bottlings"]) for p in payload)
    print(f"\nwrote {OUT.relative_to(ROOT)}: {count} cuvées over {len(payload)} producers")
    print("run `python -m scripts.build_reference` to fold them in")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("lists", nargs="*", type=Path,
                        help="rated-wine lists; defaults to the repository's own")
    parser.add_argument("--emit", action="store_true", help="write data/cuvee_additions.json")
    parser.add_argument("--limit", type=int, default=25, help="rows to print per bucket")
    args = parser.parse_args()

    if args.lists:
        missing = [p for p in args.lists if not p.exists()]
        for path in missing:
            print(f"  ! no such file: {path}", file=sys.stderr)
        rows: list = []
        for path in args.lists:
            if path.exists():
                rows.extend(read_list(path))
        if not rows:
            print("Nothing to reconcile.", file=sys.stderr)
            return 1
        print(f"Reconciling against {', '.join(p.name for p in args.lists if p.exists())}")
    else:
        rows = list(from_repo_lists())
        print("Reconciling against the repository's own top-rated lists "
              "(pass a file to use a critic list instead)")

    stats = reference()
    print(f"Cuvée database: "
          f"{sum(1 for r in stats['producers'].values() if r.get('bottlings'))} of "
          f"{len(stats['producers'])} producers carry any.")

    buckets = reconcile(rows)
    report(buckets, args.limit)
    if args.emit:
        emit(buckets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
