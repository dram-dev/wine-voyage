"""Read a retailer's product title as a wine.

A shop lists "2021 Denner Vineyards Ditch Digger Paso Robles 750ml" and means a
producer, a vintage, a cuvée and a size. Getting those back out is what lets a
public price feed be matched against a cellar.

The parse is deliberately conservative. A price attached to the wrong wine is
worse than no price, because the value tracker reports it as this bottle's worth
and computes a gain against what the owner actually paid. So a title that cannot
be resolved to a producer the reference recognises is reported, not guessed at.
"""
from __future__ import annotations

import re
from typing import Optional

from server.wine_reference import find_bottling, find_producer, normalize, reference, tokens

# A vintage, not a lot number or an address. Wine predates 1900 but a shop
# listing one is rare enough that the false positives cost more than the misses.
VINTAGE = re.compile(r"(?<!\d)(18[5-9]\d|19\d{2}|20[0-4]\d)(?!\d)")

# "750ml", "1.5L", "375 mL", "3L" — and the words shops use instead.
SIZE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(ml|cl|l|liter|litre)\b", re.I)
NAMED_SIZES = {
    "half bottle": 375, "half-bottle": 375, "split": 187, "piccolo": 187,
    "magnum": 1500, "double magnum": 3000, "jeroboam": 3000, "rehoboam": 4500,
    "methuselah": 6000, "imperial": 6000, "salmanazar": 9000,
}

# Words a shop adds that are not part of the wine's name.
TRAILING_NOISE = re.compile(
    r"\b(?:in\s+)?(?:owc|ocb|original\s+wood(?:en)?\s+case|gift\s+box|wooden\s+box|"
    r"pre[\s-]?arrival|futures|en\s+primeur|screwcap|cork|"
    r"\d+\s*(?:pack|pk|bottle\s+case|btl\s+case)|case\s+of\s+\d+)\b",
    re.I,
)


def bottle_size_ml(title: str) -> Optional[int]:
    """The size a title states, in millilitres, or None if it does not."""
    lowered = (title or "").lower()
    for phrase, ml in NAMED_SIZES.items():
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return ml
    match = SIZE.search(lowered)
    if not match:
        return None
    amount, unit = float(match.group(1)), match.group(2).lower()
    if unit == "ml":
        ml = amount
    elif unit == "cl":
        ml = amount * 10
    else:
        ml = amount * 1000
    ml = int(round(ml))
    return ml if 50 <= ml <= 30000 else None


def _strip(title: str) -> str:
    text = TRAILING_NOISE.sub(" ", title or "")
    text = SIZE.sub(" ", text)
    for phrase in NAMED_SIZES:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text, flags=re.I)
    return " ".join(text.split())


def parse_title(title: str, vendor: Optional[str] = None) -> dict:
    """Producer, vintage, cuvée and size from a shop's product title.

    `vendor` is Shopify's own producer field where the feed has one; it is far
    more reliable than anything recoverable from the title, so it wins.

    Returns `producer` only when the reference recognises it — an unmatched
    title yields `producer: None` and the caller reports it rather than
    attaching a price to a guess.
    """
    raw = " ".join((title or "").split())
    size = bottle_size_ml(raw)
    text = _strip(raw)

    vintage: Optional[int] = None
    match = VINTAGE.search(text)
    if match:
        vintage = int(match.group(1))
        text = (text[: match.start()] + " " + text[match.end():]).strip()

    # Shops write "NV" for non-vintage; that is a fact, not a missing value.
    non_vintage = bool(re.search(r"\bN\.?V\.?\b", raw, re.I))

    entry, quality = (find_producer(vendor) if vendor else (None, None))
    remainder = text
    if not entry or quality not in ("exact", "strong"):
        entry, quality, remainder = _producer_from_text(text)
    elif vendor:
        # The vendor named the producer, and the title usually repeats it — in
        # whatever spelling that shop prefers. Resolve the title's own leading
        # words too, and where they land on the same producer, keep what they
        # leave behind: otherwise "Denner" as vendor plus "Denner The Dirt
        # Worshipper" as title yields a cuvée with the producer inside it.
        from_text, quality_text, rest = _producer_from_text(text)
        if from_text and from_text["name"] == entry["name"]:
            remainder = rest
        else:
            remainder = _drop_prefix(text, entry["name"]) or text

    producer = entry["name"] if entry and quality in ("exact", "strong") else None
    cuvee = _clean_cuvee(remainder, entry) if producer else None

    return {
        "producer": producer,
        "producer_match": quality if producer else None,
        "vintage": vintage,
        "non_vintage": non_vintage and vintage is None,
        "wine_name": cuvee,
        "bottle_size_ml": size,
        "title": raw,
    }


def _producer_from_text(text: str):
    """The leading run of words the reference knows as a producer.

    A whole product title matches its own producer confidently — "Denner
    Vineyards Ditch Digger Paso Robles" contains "Denner" and leads with it — so
    taking the longest match would swallow the cuvée. A prefix only counts when
    it says nothing the producer's own name does not: "Denner Vineyards" adds
    only a noise word, "Denner Vineyards Ditch" adds a wine.

    Among the prefixes that qualify, one whose remainder names a bottling of
    that producer wins. That is what separates Ridge Vineyards' Lytton Springs
    from the "Ridge Lytton Springs" the top-rated seed lists as a producer in its
    own right: both match, only one leaves a wine behind.
    """
    words = text.split()
    candidates = []
    for length in range(1, min(len(words), 6) + 1):
        prefix = " ".join(words[:length])
        entry, quality = find_producer(prefix)
        if not entry or quality not in ("exact", "strong"):
            continue
        if not set(tokens(prefix)) <= set(tokens(entry["name"])):
            continue
        remainder = " ".join(words[length:])
        candidates.append((bool(find_bottling(entry, remainder)), length, entry, quality, remainder))

    if not candidates:
        return None, None, text
    named, _, entry, quality, remainder = max(candidates, key=lambda c: (c[0], c[1]))
    return entry, quality, remainder


def _drop_prefix(text: str, producer: str) -> Optional[str]:
    keys = normalize(producer).split()
    words = text.split()
    if len(words) >= len(keys) and [normalize(w) for w in words[: len(keys)]] == keys:
        return " ".join(words[len(keys):])
    return None


def _clean_cuvee(remainder: str, producer_entry: Optional[dict]) -> Optional[str]:
    """What is left after the producer, if it names anything.

    Where the producer's own bottlings contain a match, its canonical name is
    used, so "ditch digger paso robles" and "Ditch Digger" become one wine.
    """
    text = " ".join((remainder or "").split(" ")).strip(" -–—,")
    if not text:
        return None
    bottling = find_bottling(producer_entry, text) if producer_entry else None
    if bottling:
        return bottling["wine_name"]
    # Drop a trailing appellation the shop appended: it is place, not name.
    words = text.split()
    places = reference().get("appellations", {})
    for length in range(min(len(words), 4), 0, -1):
        if normalize(" ".join(words[-length:])) in places:
            words = words[:-length]
            break
    text = " ".join(words).strip(" -–—,")
    return text or None
