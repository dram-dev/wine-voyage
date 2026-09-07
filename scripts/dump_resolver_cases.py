"""Emit server-side resolutions for the parity harness.

    python -m scripts.dump_resolver_cases > /tmp/py.json
    node scripts/check_resolver_parity.mjs /tmp/py.json

The cases cover the shapes that have actually gone wrong: producers whose names
share a common word, a user-typed place that contradicts the producer index, a
coarse region the producer can refine, and queries with no producer at all.
"""
from __future__ import annotations

import json
import sys

from server.wine_reference import resolve

CASES: list[dict] = [
    # Plain producer lookups.
    {"producer": "Venge Vineyards", "vintage": 2023},
    {"producer": "Ridge Vineyards", "vintage": 2018},
    {"producer": "Three Sticks", "vintage": 2021},
    {"producer": "Denner", "vintage": 2020},
    {"producer": "Arista", "vintage": 2022},
    {"producer": "Chateau Margaux", "vintage": 2015},
    {"producer": "Giacomo Conterno", "vintage": 2016},
    {"producer": "Dr. Loosen", "vintage": 2020},
    {"producer": "Krug"},
    # Short forms, qualifiers, and accents.
    {"producer": "Caymus"},
    {"producer": "Venge"},
    {"producer": "Chateau Margaux 1er", "vintage": 2015},
    {"producer": "Ridge Vineyards Monte Bello", "vintage": 2018},
    {"producer": "Mondavi"},
    {"producer": "Robert Mondavi Reserve"},
    {"producer": "Piña Napa Valley"},
    # Names that merely share a common word with a real producer.
    {"producer": "Smith Family Vineyards"},
    {"producer": "Smith Family Vineyards", "region": "Oregon"},
    {"producer": "Sonoma Ridge Cellars"},
    {"producer": "Napa Valley Wine Company"},
    {"producer": "Oregon Ridge Vineyards", "vintage": 2019},
    # User-typed place vs. the producer index.
    {"producer": "Charles Smith", "region": "Oregon"},
    {"producer": "Charles Smith"},
    {"producer": "Venge Vineyards", "region": "Napa", "vintage": 2023},
    {"producer": "Venge Vineyards", "appellation": "Calistoga", "vintage": 2023},
    {"producer": "Ridge Vineyards", "region": "Sonoma", "vintage": 2018},
    # No producer, or one nobody has heard of.
    {"region": "Barolo", "vintage": 2016},
    {"appellation": "Puligny-Montrachet", "vintage": 2019},
    {"producer": "Totally Unknown Winery", "region": "Barolo", "vintage": 2016},
    {"producer": "Totally Unknown Winery", "appellation": "Los Carneros"},
    {"producer": "Totally Unknown Winery", "country": "France"},
    {"producer": "Totally Unknown Winery"},
    {},
]


def main() -> None:
    json.dump(
        [{"query": case, "result": resolve(**case)} for case in CASES],
        sys.stdout,
        default=list,
    )


if __name__ == "__main__":
    main()
