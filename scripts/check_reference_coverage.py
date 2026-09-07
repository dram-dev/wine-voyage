"""Measure what fraction of a realistic shopping list the offline reference resolves.

Autofill's offline path is a curated dataset, so its value is exactly its
coverage. This script names the wines a normal cellar holds and reports which
resolve — the number to watch when the dataset changes.

    python -m scripts.check_reference_coverage
    python -m scripts.check_reference_coverage --misses   # only what failed

Exits non-zero if coverage falls below the floor, so a regression is visible.
"""
from __future__ import annotations

import argparse
import sys

from server.wine_reference import resolve

FLOOR = 0.90

# Producers a normal cellar actually contains, across price points and countries.
SAMPLE = [
    "Caymus", "Caymus Vineyards", "Silver Oak", "Duckhorn", "Rombauer", "Opus One",
    "Venge", "Venge Vineyards", "Orin Swift", "Realm Cellars", "Shafer Vineyards",
    "Stag's Leap Wine Cellars", "Cakebread Cellars", "Far Niente", "Beringer",
    "Robert Mondavi Winery", "Chateau Montelena", "Joseph Phelps", "Frog's Leap",
    "Grgich Hills", "Dominus Estate", "Heitz Cellar", "Pride Mountain Vineyards",
    "Hess Collection", "Frank Family", "Alpha Omega", "Honig", "Hall Wines",
    "Kendall-Jackson", "La Crema", "Rodney Strong", "Seghesio", "Ramey Wine Cellars",
    "Williams Selyem", "Kistler Vineyards", "Merry Edwards", "Paul Hobbs",
    "Sonoma-Cutrer", "Jordan", "Ferrari-Carano", "Chateau St. Jean", "Benziger",
    "Ridge Vineyards", "Au Bon Climat", "Tablas Creek", "Daou", "Justin Vineyards",
    "Domaine Serene", "Domaine Drouhin Oregon", "Adelsheim", "King Estate",
    "Chateau Ste. Michelle", "Columbia Crest", "Leonetti Cellar", "DeLille Cellars",
    "Chateau Margaux", "Chateau Lafite Rothschild", "Chateau Latour", "Petrus",
    "Chateau Lynch-Bages", "Chateau Pontet-Canet", "Chateau Talbot", "Chateau Giscours",
    "Chateau Cos d'Estournel", "Chateau Haut-Brion", "Chateau d'Yquem",
    "Domaine de la Romanee-Conti", "Louis Jadot", "Joseph Drouhin", "Louis Latour",
    "William Fevre", "Domaine Leflaive", "Bouchard Pere et Fils", "Faiveley",
    "E. Guigal", "M. Chapoutier", "Paul Jaboulet Aine", "Chateau de Beaucastel",
    "Domaine Tempier", "Trimbach", "Hugel", "Domaine Zind-Humbrecht",
    "Veuve Clicquot", "Moet & Chandon", "Dom Perignon", "Krug", "Bollinger",
    "Taittinger", "Laurent-Perrier", "Perrier-Jouet", "Ruinart", "Billecart-Salmon",
    "Antinori", "Gaja", "Giacomo Conterno", "Vietti", "Produttori del Barbaresco",
    "Banfi", "Ruffino", "Frescobaldi", "Tenuta San Guido", "Ornellaia",
    "Allegrini", "Masi", "Zenato", "Pieropan", "Planeta", "Donnafugata",
    "Marques de Riscal", "La Rioja Alta", "Muga", "CVNE", "Campo Viejo",
    "Vega Sicilia", "Protos", "Alvaro Palacios", "Freixenet", "Codorniu",
    "Taylor Fladgate", "Graham's", "Dow's", "Fonseca", "Quinta do Noval", "Sandeman",
    "Dr. Loosen", "J.J. Prum", "Robert Weil", "Donnhoff", "Leitz", "Keller",
    "F.X. Pichler", "Brundlmayer", "Penfolds", "Wolf Blass", "Yalumba",
    "Henschke", "d'Arenberg", "Wynns Coonawarra Estate", "Leeuwin Estate",
    "Cape Mentelle", "Cloudy Bay", "Kim Crawford", "Oyster Bay", "Villa Maria",
    "Felton Road", "Craggy Range", "Catena Zapata", "Trapiche", "Achaval-Ferrer",
    "Concha y Toro", "Montes", "Errazuriz", "Santa Rita", "Kanonkop",
    "Boekenhoutskloof", "Meerlust", "Chateau Musar", "Royal Tokaji",
]

# California specifically: small-production labels of the kind flash-sale
# merchants (Last Bottle and its like) actually move, plus the names people
# type as a bare surname.
CALIFORNIA_SAMPLE = [
    "Three Sticks", "Denner", "Denner Vineyards", "Arista", "Arista Winery",
    "Bevan Cellars", "Carter Cellars", "Myriad Cellars", "Blankiet Estate",
    "Vineyard 29", "Melka Wines", "Memento Mori Winery", "Tor Kenward Family",
    "Larkin Wines", "Hourglass", "Kongsgaard", "Favia", "Accendo Cellars",
    "Realm Cellars", "Schrader", "Scarecrow", "Continuum", "Ovid Napa Valley",
    "Dana Estates", "Kenzo Estate", "Lewis Cellars", "Pahlmeyer", "Darioush",
    "Bedrock Wine Co.", "Carlisle Winery", "Limerick Lane", "Kamen Estate",
    "Aperture Cellars", "Cobb Wines", "Kutch Wines", "Auteur", "Benovia",
    "Martinelli", "Mauritson Wines", "Hamel Family", "Senses Wines",
    "Saxum Vineyards", "Linne Calodo", "Torrin", "Law Estate", "Booker Vineyard",
    "Herman Story", "McPrice Myers", "Villa Creek", "Jada Vineyard",
    "Alta Colina", "Caliza Winery", "Turtle Rock", "Terry Hoage",
    "Sea Smoke Cellars", "Jonata", "Stolpman Vineyards", "Tyler Winery",
    "The Hilt", "Dragonette Cellars", "Peake Ranch", "Racines", "Chanin Wine",
    "Calera", "Roar Wines", "Big Basin Vineyards", "Rhys Vineyards",
    "Michael David Winery", "Klinker Brick", "Bokisch Vineyards", "Turley Lodi",
    "Terre Rouge", "Skinner Vineyards", "Wente Vineyards", "Steven Kent",
    # Bare surnames, which is how people type them.
    "Bevan", "Carter", "Myriad", "Melka", "Saxum", "Stolpman", "Carlisle",
    "Bedrock", "Schrader", "Favia", "Torrin", "Jonata",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--misses", action="store_true", help="List only what failed")
    args = parser.parse_args()

    everything = SAMPLE + CALIFORNIA_SAMPLE
    hits, misses = [], []
    for name in everything:
        result = resolve(producer=name, vintage=2019)
        wine = result["wine"]
        if result["producer_match"] in ("exact", "strong") and wine.get("country"):
            hits.append((name, wine))
        else:
            misses.append(name)

    rate = len(hits) / len(everything)
    if not args.misses:
        for name, wine in hits:
            place = wine.get("appellation") or wine.get("region") or "—"
            print(f"  ok    {name:34} {wine['country']:15} {place}")
    for name in misses:
        print(f"  MISS  {name}")

    california = sum(1 for name in CALIFORNIA_SAMPLE
                     if resolve(producer=name, vintage=2019)["producer_match"] in ("exact", "strong"))
    print(f"\n{len(hits)}/{len(everything)} resolved ({rate:.0%}); floor is {FLOOR:.0%}")
    print(f"California subset: {california}/{len(CALIFORNIA_SAMPLE)}")
    if rate < FLOOR:
        print("Coverage is below the floor — add the missing producers to "
              "scripts/build_reference.py and regenerate.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
