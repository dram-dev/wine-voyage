"""Build data/wine_reference.json — the offline reference behind autofill.

Most of what the add-bottle form wants does not depend on the producer at all.
Country, region, typical grapes, wine type and a rough drinking window all follow
from the *appellation*. So the reference is two tables:

  appellations  the structural facts: where an appellation is, what is planted
                there, what the wine is, and how long it typically keeps
  producers     which appellation a producer works in

Given either one, the resolver can fill most of the form. Given a producer it
finds the appellation and fills everything; given only a region the user typed,
it still fills country and typical grapes rather than nothing.

The 232 producers the repository already ships in data/top_rated_*.json are
folded in automatically; the curated tables below cover the wines people
actually keep at home, which those samples (deliberately top-end) do not.

    python -m scripts.build_reference          # writes data/wine_reference.json
    python -m scripts.build_reference --check   # verify without writing
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from scripts.reference_california import CALIFORNIA_AVAS, CALIFORNIA_PRODUCERS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "wine_reference.json"
WEB_COPY = ROOT / "web" / "data" / "wine_reference.json"

# age = (years after vintage it opens, years after vintage it fades)
# grapes are the dominant plantings, most-planted first.
# fmt: off
APPELLATIONS: list[tuple] = [
    # name, region, country, type, grapes, age
    # ---- France: Bordeaux ----
    ("Bordeaux", "Bordeaux", "France", "red", ["Merlot", "Cabernet Sauvignon", "Cabernet Franc"], (3, 15)),
    ("Medoc", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (5, 25)),
    ("Haut-Medoc", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (5, 25)),
    ("Margaux", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot", "Petit Verdot"], (8, 40)),
    ("Pauillac", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (10, 45)),
    ("Saint-Julien", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (8, 40)),
    ("Saint-Estephe", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (10, 40)),
    ("Pessac-Leognan", "Bordeaux", "France", "red", ["Cabernet Sauvignon", "Merlot"], (8, 35)),
    ("Graves", "Bordeaux", "France", "red", ["Merlot", "Cabernet Sauvignon"], (5, 20)),
    ("Pomerol", "Bordeaux", "France", "red", ["Merlot", "Cabernet Franc"], (8, 35)),
    ("Saint-Emilion", "Bordeaux", "France", "red", ["Merlot", "Cabernet Franc"], (7, 30)),
    ("Sauternes", "Bordeaux", "France", "dessert", ["Semillon", "Sauvignon Blanc"], (5, 50)),
    # ---- France: Burgundy ----
    ("Bourgogne", "Burgundy", "France", "red", ["Pinot Noir"], (2, 8)),
    ("Chablis", "Burgundy", "France", "white", ["Chardonnay"], (2, 12)),
    ("Gevrey-Chambertin", "Burgundy", "France", "red", ["Pinot Noir"], (6, 25)),
    ("Chambolle-Musigny", "Burgundy", "France", "red", ["Pinot Noir"], (6, 25)),
    ("Vosne-Romanee", "Burgundy", "France", "red", ["Pinot Noir"], (7, 30)),
    ("Nuits-Saint-Georges", "Burgundy", "France", "red", ["Pinot Noir"], (6, 25)),
    ("Morey-Saint-Denis", "Burgundy", "France", "red", ["Pinot Noir"], (6, 25)),
    ("Volnay", "Burgundy", "France", "red", ["Pinot Noir"], (5, 20)),
    ("Pommard", "Burgundy", "France", "red", ["Pinot Noir"], (6, 22)),
    ("Beaune", "Burgundy", "France", "red", ["Pinot Noir"], (4, 18)),
    ("Meursault", "Burgundy", "France", "white", ["Chardonnay"], (3, 15)),
    ("Puligny-Montrachet", "Burgundy", "France", "white", ["Chardonnay"], (4, 18)),
    ("Chassagne-Montrachet", "Burgundy", "France", "white", ["Chardonnay"], (3, 16)),
    ("Pouilly-Fuisse", "Burgundy", "France", "white", ["Chardonnay"], (2, 10)),
    ("Macon", "Burgundy", "France", "white", ["Chardonnay"], (1, 6)),
    ("Beaujolais", "Beaujolais", "France", "red", ["Gamay"], (1, 5)),
    ("Morgon", "Beaujolais", "France", "red", ["Gamay"], (2, 12)),
    ("Fleurie", "Beaujolais", "France", "red", ["Gamay"], (2, 10)),
    # ---- France: Rhone ----
    ("Cote-Rotie", "Rhone", "France", "red", ["Syrah", "Viognier"], (7, 30)),
    ("Hermitage", "Rhone", "France", "red", ["Syrah"], (8, 35)),
    ("Crozes-Hermitage", "Rhone", "France", "red", ["Syrah"], (3, 15)),
    ("Cornas", "Rhone", "France", "red", ["Syrah"], (6, 25)),
    ("Saint-Joseph", "Rhone", "France", "red", ["Syrah"], (4, 18)),
    ("Condrieu", "Rhone", "France", "white", ["Viognier"], (1, 8)),
    ("Chateauneuf-du-Pape", "Rhone", "France", "red", ["Grenache", "Syrah", "Mourvedre"], (6, 28)),
    ("Gigondas", "Rhone", "France", "red", ["Grenache", "Syrah", "Mourvedre"], (4, 18)),
    ("Vacqueyras", "Rhone", "France", "red", ["Grenache", "Syrah"], (3, 14)),
    ("Cotes du Rhone", "Rhone", "France", "red", ["Grenache", "Syrah", "Mourvedre"], (1, 7)),
    ("Tavel", "Rhone", "France", "rose", ["Grenache", "Cinsault"], (0, 4)),
    # ---- France: elsewhere ----
    ("Champagne", "Champagne", "France", "sparkling", ["Chardonnay", "Pinot Noir", "Pinot Meunier"], (2, 20)),
    ("Sancerre", "Loire", "France", "white", ["Sauvignon Blanc"], (1, 8)),
    ("Pouilly-Fume", "Loire", "France", "white", ["Sauvignon Blanc"], (1, 8)),
    ("Vouvray", "Loire", "France", "white", ["Chenin Blanc"], (2, 25)),
    ("Chinon", "Loire", "France", "red", ["Cabernet Franc"], (3, 15)),
    ("Bourgueil", "Loire", "France", "red", ["Cabernet Franc"], (3, 15)),
    ("Muscadet", "Loire", "France", "white", ["Melon de Bourgogne"], (1, 8)),
    ("Savennieres", "Loire", "France", "white", ["Chenin Blanc"], (3, 20)),
    ("Alsace", "Alsace", "France", "white", ["Riesling", "Gewurztraminer", "Pinot Gris"], (2, 15)),
    ("Cotes de Provence", "Provence", "France", "rose", ["Grenache", "Cinsault", "Syrah"], (0, 3)),
    ("Bandol", "Provence", "France", "red", ["Mourvedre", "Grenache"], (5, 20)),
    ("Cahors", "South West France", "France", "red", ["Malbec"], (3, 15)),
    ("Madiran", "South West France", "France", "red", ["Tannat"], (5, 20)),
    ("Languedoc", "Languedoc-Roussillon", "France", "red", ["Syrah", "Grenache", "Carignan"], (2, 10)),
    ("Corbieres", "Languedoc-Roussillon", "France", "red", ["Carignan", "Grenache", "Syrah"], (2, 10)),
    # ---- Italy ----
    ("Barolo", "Piedmont", "Italy", "red", ["Nebbiolo"], (8, 35)),
    ("Barbaresco", "Piedmont", "Italy", "red", ["Nebbiolo"], (6, 30)),
    ("Barbera d'Alba", "Piedmont", "Italy", "red", ["Barbera"], (2, 12)),
    ("Barbera d'Asti", "Piedmont", "Italy", "red", ["Barbera"], (2, 12)),
    ("Dolcetto d'Alba", "Piedmont", "Italy", "red", ["Dolcetto"], (1, 6)),
    ("Gavi", "Piedmont", "Italy", "white", ["Cortese"], (1, 5)),
    ("Langhe", "Piedmont", "Italy", "red", ["Nebbiolo"], (2, 12)),
    ("Chianti", "Tuscany", "Italy", "red", ["Sangiovese"], (2, 10)),
    ("Chianti Classico", "Tuscany", "Italy", "red", ["Sangiovese"], (3, 18)),
    ("Brunello di Montalcino", "Tuscany", "Italy", "red", ["Sangiovese"], (8, 35)),
    ("Rosso di Montalcino", "Tuscany", "Italy", "red", ["Sangiovese"], (2, 10)),
    ("Vino Nobile di Montepulciano", "Tuscany", "Italy", "red", ["Sangiovese"], (4, 18)),
    ("Bolgheri", "Tuscany", "Italy", "red", ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"], (5, 25)),
    ("Maremma", "Tuscany", "Italy", "red", ["Sangiovese", "Cabernet Sauvignon"], (3, 15)),
    ("Amarone della Valpolicella", "Veneto", "Italy", "red", ["Corvina", "Rondinella"], (6, 30)),
    ("Valpolicella", "Veneto", "Italy", "red", ["Corvina", "Rondinella"], (1, 8)),
    ("Soave", "Veneto", "Italy", "white", ["Garganega"], (1, 8)),
    ("Prosecco", "Veneto", "Italy", "sparkling", ["Glera"], (0, 3)),
    ("Franciacorta", "Lombardy", "Italy", "sparkling", ["Chardonnay", "Pinot Noir"], (2, 12)),
    ("Etna", "Sicily", "Italy", "red", ["Nerello Mascalese"], (3, 18)),
    ("Sicilia", "Sicily", "Italy", "red", ["Nero d'Avola"], (2, 10)),
    ("Montepulciano d'Abruzzo", "Abruzzo", "Italy", "red", ["Montepulciano"], (2, 12)),
    ("Taurasi", "Campania", "Italy", "red", ["Aglianico"], (6, 25)),
    ("Alto Adige", "Alto Adige", "Italy", "white", ["Pinot Grigio", "Gewurztraminer"], (1, 8)),
    ("Friuli", "Friuli", "Italy", "white", ["Friulano", "Pinot Grigio"], (1, 8)),
    # ---- Spain & Portugal ----
    ("Rioja", "Rioja", "Spain", "red", ["Tempranillo", "Garnacha"], (3, 20)),
    ("Ribera del Duero", "Castilla y Leon", "Spain", "red", ["Tempranillo"], (4, 22)),
    ("Priorat", "Catalonia", "Spain", "red", ["Garnacha", "Carinena"], (5, 22)),
    ("Rias Baixas", "Galicia", "Spain", "white", ["Albarino"], (1, 6)),
    ("Rueda", "Castilla y Leon", "Spain", "white", ["Verdejo"], (1, 5)),
    ("Toro", "Castilla y Leon", "Spain", "red", ["Tempranillo"], (3, 15)),
    ("Cava", "Catalonia", "Spain", "sparkling", ["Macabeo", "Xarel-lo", "Parellada"], (0, 5)),
    ("Jerez", "Andalusia", "Spain", "fortified", ["Palomino"], (0, 20)),
    ("Porto", "Douro", "Portugal", "fortified", ["Touriga Nacional", "Touriga Franca"], (10, 50)),
    ("Douro", "Douro", "Portugal", "red", ["Touriga Nacional", "Touriga Franca"], (3, 20)),
    ("Dao", "Dao", "Portugal", "red", ["Touriga Nacional"], (3, 15)),
    ("Vinho Verde", "Minho", "Portugal", "white", ["Alvarinho", "Loureiro"], (0, 3)),
    ("Madeira", "Madeira", "Portugal", "fortified", ["Sercial", "Verdelho", "Bual", "Malmsey"], (0, 100)),
    # ---- Germany & Austria ----
    ("Mosel", "Mosel", "Germany", "white", ["Riesling"], (2, 25)),
    ("Rheingau", "Rheingau", "Germany", "white", ["Riesling"], (2, 25)),
    ("Pfalz", "Pfalz", "Germany", "white", ["Riesling"], (2, 20)),
    ("Rheinhessen", "Rheinhessen", "Germany", "white", ["Riesling"], (2, 18)),
    ("Nahe", "Nahe", "Germany", "white", ["Riesling"], (2, 20)),
    ("Baden", "Baden", "Germany", "red", ["Pinot Noir"], (2, 15)),
    ("Wachau", "Wachau", "Austria", "white", ["Gruner Veltliner", "Riesling"], (2, 18)),
    ("Kamptal", "Kamptal", "Austria", "white", ["Gruner Veltliner", "Riesling"], (2, 15)),
    ("Burgenland", "Burgenland", "Austria", "red", ["Blaufrankisch"], (3, 15)),
    # ---- United States ----
    ("Napa Valley", "Napa", "United States", "red", ["Cabernet Sauvignon", "Merlot"], (4, 22)),
    ("Oakville", "Napa", "United States", "red", ["Cabernet Sauvignon"], (6, 28)),
    ("Rutherford", "Napa", "United States", "red", ["Cabernet Sauvignon"], (6, 28)),
    ("Stags Leap District", "Napa", "United States", "red", ["Cabernet Sauvignon"], (5, 25)),
    ("Howell Mountain", "Napa", "United States", "red", ["Cabernet Sauvignon"], (7, 30)),
    ("Spring Mountain District", "Napa", "United States", "red", ["Cabernet Sauvignon"], (6, 28)),
    ("Diamond Mountain District", "Napa", "United States", "red", ["Cabernet Sauvignon"], (6, 28)),
    ("Mount Veeder", "Napa", "United States", "red", ["Cabernet Sauvignon"], (6, 28)),
    ("Calistoga", "Napa", "United States", "red", ["Cabernet Sauvignon"], (5, 25)),
    ("St. Helena", "Napa", "United States", "red", ["Cabernet Sauvignon"], (5, 25)),
    ("Yountville", "Napa", "United States", "red", ["Cabernet Sauvignon", "Merlot"], (5, 24)),
    ("Carneros", "Napa", "United States", "red", ["Pinot Noir", "Chardonnay"], (2, 12)),
    ("Sonoma County", "Sonoma", "United States", "red", ["Cabernet Sauvignon", "Zinfandel"], (3, 15)),
    ("Russian River Valley", "Sonoma", "United States", "red", ["Pinot Noir", "Chardonnay"], (3, 15)),
    ("Alexander Valley", "Sonoma", "United States", "red", ["Cabernet Sauvignon"], (4, 20)),
    ("Dry Creek Valley", "Sonoma", "United States", "red", ["Zinfandel"], (3, 15)),
    ("Sonoma Coast", "Sonoma", "United States", "red", ["Pinot Noir", "Chardonnay"], (3, 15)),
    ("Knights Valley", "Sonoma", "United States", "red", ["Cabernet Sauvignon"], (4, 20)),
    ("Chalk Hill", "Sonoma", "United States", "white", ["Chardonnay"], (2, 10)),
    ("Anderson Valley", "Mendocino", "United States", "red", ["Pinot Noir"], (3, 15)),
    ("Santa Cruz Mountains", "Central Coast", "United States", "red", ["Cabernet Sauvignon", "Pinot Noir"], (5, 25)),
    ("Santa Barbara County", "Central Coast", "United States", "red", ["Pinot Noir", "Chardonnay"], (2, 12)),
    ("Sta. Rita Hills", "Central Coast", "United States", "red", ["Pinot Noir", "Chardonnay"], (3, 15)),
    ("Santa Lucia Highlands", "Central Coast", "United States", "red", ["Pinot Noir", "Chardonnay"], (3, 15)),
    ("Paso Robles", "Central Coast", "United States", "red", ["Cabernet Sauvignon", "Syrah", "Zinfandel"], (3, 16)),
    ("Edna Valley", "Central Coast", "United States", "white", ["Chardonnay"], (2, 10)),
    ("Willamette Valley", "Oregon", "United States", "red", ["Pinot Noir"], (3, 16)),
    ("Dundee Hills", "Oregon", "United States", "red", ["Pinot Noir"], (3, 18)),
    ("Columbia Valley", "Washington", "United States", "red", ["Cabernet Sauvignon", "Merlot", "Syrah"], (3, 18)),
    ("Walla Walla Valley", "Washington", "United States", "red", ["Cabernet Sauvignon", "Syrah"], (4, 20)),
    ("Red Mountain", "Washington", "United States", "red", ["Cabernet Sauvignon"], (5, 22)),
    ("Finger Lakes", "New York", "United States", "white", ["Riesling"], (2, 12)),
    # ---- Southern hemisphere ----
    ("Barossa Valley", "South Australia", "Australia", "red", ["Shiraz", "Grenache"], (4, 25)),
    ("McLaren Vale", "South Australia", "Australia", "red", ["Shiraz", "Grenache"], (3, 18)),
    ("Clare Valley", "South Australia", "Australia", "white", ["Riesling"], (2, 20)),
    ("Eden Valley", "South Australia", "Australia", "white", ["Riesling"], (2, 20)),
    ("Coonawarra", "South Australia", "Australia", "red", ["Cabernet Sauvignon"], (5, 25)),
    ("Margaret River", "Western Australia", "Australia", "red", ["Cabernet Sauvignon", "Chardonnay"], (4, 20)),
    ("Yarra Valley", "Victoria", "Australia", "red", ["Pinot Noir", "Chardonnay"], (3, 15)),
    ("Hunter Valley", "New South Wales", "Australia", "white", ["Semillon"], (3, 20)),
    ("Marlborough", "Marlborough", "New Zealand", "white", ["Sauvignon Blanc"], (0, 5)),
    ("Central Otago", "Central Otago", "New Zealand", "red", ["Pinot Noir"], (3, 15)),
    ("Hawke's Bay", "Hawke's Bay", "New Zealand", "red", ["Merlot", "Cabernet Sauvignon", "Syrah"], (3, 15)),
    ("Mendoza", "Mendoza", "Argentina", "red", ["Malbec"], (3, 15)),
    ("Uco Valley", "Mendoza", "Argentina", "red", ["Malbec"], (4, 18)),
    ("Maipo Valley", "Maipo", "Chile", "red", ["Cabernet Sauvignon"], (3, 18)),
    ("Colchagua Valley", "Colchagua", "Chile", "red", ["Cabernet Sauvignon", "Carmenere"], (3, 16)),
    ("Casablanca Valley", "Casablanca", "Chile", "white", ["Sauvignon Blanc", "Chardonnay"], (1, 6)),
    ("Bekaa Valley", "Bekaa", "Lebanon", "red", ["Cabernet Sauvignon", "Cinsault", "Carignan"], (5, 25)),
    ("Tokaj", "Tokaj", "Hungary", "dessert", ["Furmint", "Harslevelu"], (5, 40)),
    ("Santorini", "Santorini", "Greece", "white", ["Assyrtiko"], (2, 15)),
    ("Nemea", "Peloponnese", "Greece", "red", ["Agiorgitiko"], (2, 12)),
    ("Stellenbosch", "Western Cape", "South Africa", "red", ["Cabernet Sauvignon", "Syrah"], (3, 18)),
    ("Swartland", "Western Cape", "South Africa", "red", ["Syrah", "Chenin Blanc"], (3, 15)),
]

# Producers people actually keep at home. The repository's top_rated_*.json
# samples are deliberately top-end, so this covers the everyday shelf.
PRODUCERS: list[tuple[str, str]] = [
    # -- Napa / Sonoma --
    ("Caymus Vineyards", "Napa Valley"), ("Silver Oak", "Alexander Valley"),
    ("Duckhorn Vineyards", "Napa Valley"), ("Rombauer Vineyards", "Napa Valley"),
    ("Opus One", "Oakville"), ("Stag's Leap Wine Cellars", "Stags Leap District"),
    ("Cakebread Cellars", "Rutherford"), ("Far Niente", "Oakville"),
    ("Beringer", "Napa Valley"), ("Robert Mondavi Winery", "Oakville"),
    ("Heitz Cellar", "Napa Valley"), ("Chateau Montelena", "Calistoga"),
    ("Shafer Vineyards", "Stags Leap District"), ("Joseph Phelps", "Napa Valley"),
    ("Frog's Leap", "Rutherford"), ("Grgich Hills", "Rutherford"),
    ("Quintessa", "Rutherford"), ("Dominus Estate", "Yountville"),
    ("Screaming Eagle", "Oakville"), ("Harlan Estate", "Oakville"),
    ("Spottswoode", "St. Helena"), ("Corison", "St. Helena"),
    ("Dunn Vineyards", "Howell Mountain"), ("Ridge Vineyards", "Santa Cruz Mountains"),
    ("Silverado Vineyards", "Stags Leap District"), ("Trefethen", "Napa Valley"),
    ("Stag's Leap Winery", "Stags Leap District"), ("Clos Du Val", "Stags Leap District"),
    ("Jordan Vineyard & Winery", "Alexander Valley"),
    ("Kendall-Jackson", "Sonoma County"), ("La Crema", "Sonoma Coast"),
    ("Rodney Strong", "Sonoma County"), ("Ravenswood", "Sonoma County"),
    ("Seghesio", "Dry Creek Valley"), ("Dry Creek Vineyard", "Dry Creek Valley"),
    ("Williams Selyem", "Russian River Valley"), ("Rochioli", "Russian River Valley"),
    ("Kistler Vineyards", "Russian River Valley"), ("Merry Edwards", "Russian River Valley"),
    ("Kosta Browne", "Russian River Valley"), ("Gary Farrell", "Russian River Valley"),
    ("Iron Horse Vineyards", "Russian River Valley"), ("Flowers", "Sonoma Coast"),
    ("Hirsch Vineyards", "Sonoma Coast"), ("Littorai", "Sonoma Coast"),
    ("Duckhorn", "Napa Valley"), ("Chappellet", "Napa Valley"),
    ("Nickel & Nickel", "Oakville"), ("Turley Wine Cellars", "Napa Valley"),
    ("Schramsberg", "Calistoga"), ("Domaine Carneros", "Carneros"),
    ("Sinskey", "Carneros"), ("Hyde de Villaine", "Carneros"),
    # -- Central Coast / other US --
    ("Au Bon Climat", "Santa Barbara County"), ("Sanford", "Sta. Rita Hills"),
    ("Bonny Doon", "Santa Cruz Mountains"), ("Mount Eden Vineyards", "Santa Cruz Mountains"),
    ("Tablas Creek", "Adelaida District"), ("Justin Vineyards", "Adelaida District"),
    ("Saxum", "Willow Creek District"), ("Alban Vineyards", "Edna Valley"),
    ("Domaine de la Cote", "Sta. Rita Hills"), ("Sandhi", "Sta. Rita Hills"),
    ("Talley Vineyards", "Edna Valley"), ("Ceritas", "Sonoma Coast"),
    ("Domaine Drouhin Oregon", "Dundee Hills"), ("Ponzi Vineyards", "Willamette Valley"),
    ("Bethel Heights", "Willamette Valley"), ("Cristom", "Willamette Valley"),
    ("Beaux Freres", "Willamette Valley"), ("Argyle", "Willamette Valley"),
    ("Chateau Ste. Michelle", "Columbia Valley"), ("Leonetti Cellar", "Walla Walla Valley"),
    ("Quilceda Creek", "Columbia Valley"), ("Cayuse Vineyards", "Walla Walla Valley"),
    ("L'Ecole No 41", "Walla Walla Valley"), ("Dr. Konstantin Frank", "Finger Lakes"),
    ("Hermann J. Wiemer", "Finger Lakes"),
    # -- Bordeaux --
    ("Chateau Margaux", "Margaux"), ("Chateau Palmer", "Margaux"),
    ("Chateau Lafite Rothschild", "Pauillac"), ("Chateau Latour", "Pauillac"),
    ("Chateau Mouton Rothschild", "Pauillac"), ("Chateau Pichon Baron", "Pauillac"),
    ("Chateau Pichon Lalande", "Pauillac"), ("Chateau Lynch-Bages", "Pauillac"),
    ("Chateau Pontet-Canet", "Pauillac"), ("Chateau Grand-Puy-Lacoste", "Pauillac"),
    ("Chateau Leoville-Las Cases", "Saint-Julien"), ("Chateau Leoville Barton", "Saint-Julien"),
    ("Chateau Ducru-Beaucaillou", "Saint-Julien"), ("Chateau Gruaud-Larose", "Saint-Julien"),
    ("Chateau Beychevelle", "Saint-Julien"), ("Chateau Talbot", "Saint-Julien"),
    ("Chateau Cos d'Estournel", "Saint-Estephe"), ("Chateau Montrose", "Saint-Estephe"),
    ("Chateau Calon-Segur", "Saint-Estephe"), ("Chateau Haut-Brion", "Pessac-Leognan"),
    ("Chateau La Mission Haut-Brion", "Pessac-Leognan"), ("Domaine de Chevalier", "Pessac-Leognan"),
    ("Chateau Smith Haut Lafitte", "Pessac-Leognan"), ("Petrus", "Pomerol"),
    ("Chateau Le Pin", "Pomerol"), ("Chateau Lafleur", "Pomerol"),
    ("Vieux Chateau Certan", "Pomerol"), ("Chateau Trotanoy", "Pomerol"),
    ("Chateau Cheval Blanc", "Saint-Emilion"), ("Chateau Ausone", "Saint-Emilion"),
    ("Chateau Angelus", "Saint-Emilion"), ("Chateau Figeac", "Saint-Emilion"),
    ("Chateau Pavie", "Saint-Emilion"), ("Chateau d'Yquem", "Sauternes"),
    ("Chateau Climens", "Sauternes"), ("Chateau Suduiraut", "Sauternes"),
    # -- Burgundy --
    ("Domaine de la Romanee-Conti", "Vosne-Romanee"), ("Domaine Leroy", "Vosne-Romanee"),
    ("Domaine Armand Rousseau", "Gevrey-Chambertin"), ("Domaine Dujac", "Morey-Saint-Denis"),
    ("Domaine Georges Roumier", "Chambolle-Musigny"), ("Domaine Comte Georges de Vogue", "Chambolle-Musigny"),
    ("Domaine Leflaive", "Puligny-Montrachet"), ("Domaine Coche-Dury", "Meursault"),
    ("Domaine des Comtes Lafon", "Meursault"), ("Louis Jadot", "Beaune"),
    ("Joseph Drouhin", "Beaune"), ("Bouchard Pere et Fils", "Beaune"),
    ("Faiveley", "Nuits-Saint-Georges"), ("Domaine Meo-Camuzet", "Vosne-Romanee"),
    ("Domaine Ponsot", "Morey-Saint-Denis"), ("Domaine Marquis d'Angerville", "Volnay"),
    ("William Fevre", "Chablis"), ("Domaine Raveneau", "Chablis"),
    ("Domaine Vincent Dauvissat", "Chablis"), ("Louis Latour", "Beaune"),
    ("Olivier Leflaive", "Puligny-Montrachet"), ("Domaine Ramonet", "Chassagne-Montrachet"),
    # -- Rhone / Loire / Alsace / Champagne --
    ("E. Guigal", "Cote-Rotie"), ("Domaine Jean-Louis Chave", "Hermitage"),
    ("M. Chapoutier", "Hermitage"), ("Paul Jaboulet Aine", "Hermitage"),
    ("Rene Rostaing", "Cote-Rotie"), ("Domaine Auguste Clape", "Cornas"),
    ("Chateau de Beaucastel", "Chateauneuf-du-Pape"), ("Domaine du Vieux Telegraphe", "Chateauneuf-du-Pape"),
    ("Chateau Rayas", "Chateauneuf-du-Pape"), ("Clos des Papes", "Chateauneuf-du-Pape"),
    ("Domaine du Pegau", "Chateauneuf-du-Pape"), ("Domaine Tempier", "Bandol"),
    ("Didier Dagueneau", "Pouilly-Fume"), ("Domaine Vacheron", "Sancerre"),
    ("Henri Bourgeois", "Sancerre"), ("Domaine Huet", "Vouvray"),
    ("Nicolas Joly", "Savennieres"), ("Trimbach", "Alsace"),
    ("Domaine Weinbach", "Alsace"), ("Domaine Zind-Humbrecht", "Alsace"),
    ("Hugel", "Alsace"), ("Krug", "Champagne"), ("Dom Perignon", "Champagne"),
    ("Bollinger", "Champagne"), ("Louis Roederer", "Champagne"), ("Pol Roger", "Champagne"),
    ("Veuve Clicquot", "Champagne"), ("Moet & Chandon", "Champagne"),
    ("Taittinger", "Champagne"), ("Perrier-Jouet", "Champagne"), ("Ruinart", "Champagne"),
    ("Billecart-Salmon", "Champagne"), ("Jacques Selosse", "Champagne"),
    ("Salon", "Champagne"), ("Philipponnat", "Champagne"), ("Laurent-Perrier", "Champagne"),
    ("Piper-Heidsieck", "Champagne"), ("Charles Heidsieck", "Champagne"),
    ("Gosset", "Champagne"), ("Egly-Ouriet", "Champagne"), ("Vilmart & Cie", "Champagne"),
    # -- Italy --
    ("Giacomo Conterno", "Barolo"), ("Bruno Giacosa", "Barbaresco"),
    ("Gaja", "Barbaresco"), ("Produttori del Barbaresco", "Barbaresco"),
    ("Vietti", "Barolo"), ("G.D. Vajra", "Barolo"), ("Massolino", "Barolo"),
    ("Paolo Scavino", "Barolo"), ("Bartolo Mascarello", "Barolo"),
    ("Giuseppe Mascarello", "Barolo"), ("Elio Grasso", "Barolo"),
    ("Pio Cesare", "Barolo"), ("Marchesi di Barolo", "Barolo"),
    ("Antinori", "Chianti Classico"), ("Castello di Ama", "Chianti Classico"),
    ("Fontodi", "Chianti Classico"), ("Isole e Olena", "Chianti Classico"),
    ("Felsina", "Chianti Classico"), ("Ruffino", "Chianti Classico"),
    ("Biondi-Santi", "Brunello di Montalcino"), ("Soldera", "Brunello di Montalcino"),
    ("Casanova di Neri", "Brunello di Montalcino"), ("Il Poggione", "Brunello di Montalcino"),
    ("Banfi", "Brunello di Montalcino"), ("Tenuta San Guido", "Bolgheri"),
    ("Ornellaia", "Bolgheri"), ("Tenuta dell'Ornellaia", "Bolgheri"),
    ("Le Macchiole", "Bolgheri"), ("Quintarelli", "Amarone della Valpolicella"),
    ("Giuseppe Quintarelli", "Amarone della Valpolicella"), ("Dal Forno Romano", "Amarone della Valpolicella"),
    ("Allegrini", "Valpolicella"), ("Masi", "Valpolicella"),
    ("Emidio Pepe", "Montepulciano d'Abruzzo"), ("Valentini", "Montepulciano d'Abruzzo"),
    ("Passopisciaro", "Etna"), ("Benanti", "Etna"), ("Planeta", "Sicilia"),
    ("Ca' del Bosco", "Franciacorta"), ("Bellavista", "Franciacorta"),
    ("Jermann", "Friuli"), ("Alois Lageder", "Alto Adige"),
    # -- Spain / Portugal --
    ("Vega Sicilia", "Ribera del Duero"), ("Pingus", "Ribera del Duero"),
    ("Dominio de Pingus", "Ribera del Duero"), ("Alion", "Ribera del Duero"),
    ("Tinto Pesquera", "Ribera del Duero"), ("Emilio Moro", "Ribera del Duero"),
    ("La Rioja Alta", "Rioja"), ("Lopez de Heredia", "Rioja"),
    ("R. Lopez de Heredia", "Rioja"), ("Marques de Riscal", "Rioja"),
    ("Marques de Murrieta", "Rioja"), ("CVNE", "Rioja"), ("Muga", "Rioja"),
    ("Bodegas Muga", "Rioja"), ("Artadi", "Rioja"), ("Remelluri", "Rioja"),
    ("Alvaro Palacios", "Priorat"), ("Clos Mogador", "Priorat"),
    ("Pazo Senorans", "Rias Baixas"), ("Albarino de Fefinanes", "Rias Baixas"),
    ("Gonzalez Byass", "Jerez"), ("Lustau", "Jerez"), ("Equipo Navazos", "Jerez"),
    ("Taylor Fladgate", "Porto"), ("Fonseca", "Porto"), ("Graham's", "Porto"),
    ("Dow's", "Porto"), ("Warre's", "Porto"), ("Quinta do Noval", "Porto"),
    ("Niepoort", "Douro"), ("Quinta do Crasto", "Douro"), ("Barca Velha", "Douro"),
    ("Blandy's", "Madeira"), ("Barbeito", "Madeira"),
    # -- Germany / Austria --
    ("Dr. Loosen", "Mosel"), ("Egon Muller", "Mosel"), ("Joh. Jos. Prum", "Mosel"),
    ("J.J. Prum", "Mosel"), ("Willi Schaefer", "Mosel"), ("Selbach-Oster", "Mosel"),
    ("Markus Molitor", "Mosel"), ("Robert Weil", "Rheingau"),
    ("Schloss Johannisberg", "Rheingau"), ("Georg Breuer", "Rheingau"),
    ("Keller", "Rheinhessen"), ("Wittmann", "Rheinhessen"),
    ("Donnhoff", "Nahe"), ("Emrich-Schonleber", "Nahe"),
    ("Dr. Burklin-Wolf", "Pfalz"), ("Muller-Catoir", "Pfalz"),
    ("F.X. Pichler", "Wachau"), ("Knoll", "Wachau"), ("Prager", "Wachau"),
    ("Hirtzberger", "Wachau"), ("Brundlmayer", "Kamptal"), ("Schloss Gobelsburg", "Kamptal"),
    # -- Southern hemisphere --
    ("Penfolds", "Barossa Valley"), ("Henschke", "Eden Valley"),
    ("Torbreck", "Barossa Valley"), ("Peter Lehmann", "Barossa Valley"),
    ("Yalumba", "Barossa Valley"), ("Jim Barry", "Clare Valley"),
    ("Grosset", "Clare Valley"), ("d'Arenberg", "McLaren Vale"),
    ("Wynns Coonawarra Estate", "Coonawarra"), ("Cape Mentelle", "Margaret River"),
    ("Leeuwin Estate", "Margaret River"), ("Vasse Felix", "Margaret River"),
    ("Cullen Wines", "Margaret River"), ("Moss Wood", "Margaret River"),
    ("Giant Steps", "Yarra Valley"), ("Mount Mary", "Yarra Valley"),
    ("Tyrrell's", "Hunter Valley"), ("Cloudy Bay", "Marlborough"),
    ("Kim Crawford", "Marlborough"), ("Oyster Bay", "Marlborough"),
    ("Dog Point", "Marlborough"), ("Greywacke", "Marlborough"),
    ("Villa Maria", "Marlborough"), ("Felton Road", "Central Otago"),
    ("Rippon", "Central Otago"), ("Craggy Range", "Hawke's Bay"),
    ("Catena Zapata", "Mendoza"), ("Bodega Catena Zapata", "Mendoza"),
    ("Achaval-Ferrer", "Mendoza"), ("Zuccardi", "Uco Valley"),
    ("Cheval des Andes", "Mendoza"), ("Trapiche", "Mendoza"),
    ("Concha y Toro", "Maipo Valley"), ("Almaviva", "Maipo Valley"),
    ("Errazuriz", "Colchagua Valley"), ("Montes", "Colchagua Valley"),
    ("Casa Lapostolle", "Colchagua Valley"), ("Kanonkop", "Stellenbosch"),
    # -- Lebanon, Hungary, Greece --
    ("Chateau Musar", "Bekaa Valley"), ("Massaya", "Bekaa Valley"),
    ("Royal Tokaji", "Tokaj"), ("Disznoko", "Tokaj"),
    ("Domaine Sigalas", "Santorini"), ("Gaia Wines", "Santorini"),
    ("Meerlust", "Stellenbosch"), ("Rust en Vrede", "Stellenbosch"),
    ("Sadie Family", "Swartland"), ("Klein Constantia", "Stellenbosch"),
]
# A second pass, weighted to what people actually keep at home rather than what
# scores well. Napa and Sonoma dominate because US cellars do.
PRODUCERS += [
    # -- Napa --
    ("Venge Vineyards", "Calistoga"), ("Saddleback Cellars", "Oakville"),
    ("Hundred Acre", "Napa Valley"), ("Schrader Cellars", "Oakville"),
    ("Colgin", "Napa Valley"), ("Bryant Family", "Napa Valley"),
    ("Bond Estates", "Napa Valley"), ("Promontory", "Oakville"),
    ("Continuum", "Napa Valley"), ("Ovid", "Napa Valley"),
    ("Realm Cellars", "Napa Valley"), ("Scarecrow", "Rutherford"),
    ("Maybach", "Napa Valley"), ("Kapcsandy", "Yountville"),
    ("Vine Hill Ranch", "Oakville"), ("Futo", "Oakville"),
    ("Dalla Valle", "Oakville"), ("Plumpjack", "Oakville"),
    ("Cade", "Howell Mountain"), ("Odette", "Stags Leap District"),
    ("Chimney Rock", "Stags Leap District"), ("Pine Ridge", "Stags Leap District"),
    ("Cliff Lede", "Stags Leap District"), ("Baldacci", "Stags Leap District"),
    ("Robert Sinskey Vineyards", "Carneros"), ("Etude", "Carneros"),
    ("Artesa", "Carneros"), ("Bouchaine", "Carneros"),
    ("Cuvaison", "Carneros"), ("Truchard", "Carneros"),
    ("Freemark Abbey", "St. Helena"), ("Charles Krug", "St. Helena"),
    ("Louis M. Martini", "Napa Valley"), ("Duckhorn Wine Company", "Napa Valley"),
    ("Paraduxx", "Napa Valley"), ("Migration", "Napa Valley"),
    ("Rutherford Hill", "Rutherford"), ("Round Pond", "Rutherford"),
    ("Inglenook", "Rutherford"), ("Alpha Omega", "Rutherford"),
    ("Sequoia Grove", "Rutherford"), ("Honig", "Rutherford"),
    ("Peju", "Rutherford"), ("Mumm Napa", "Rutherford"),
    ("ZD Wines", "Napa Valley"), ("Stony Hill", "Napa Valley"),
    ("Smith-Madrone", "Spring Mountain District"), ("Pride Mountain Vineyards", "Spring Mountain District"),
    ("Barnett Vineyards", "Spring Mountain District"), ("Cain Vineyard", "Spring Mountain District"),
    ("Diamond Creek", "Diamond Mountain District"), ("Von Strasser", "Diamond Mountain District"),
    ("Hess Collection", "Mount Veeder"), ("Mayacamas", "Mount Veeder"),
    ("Lokoya", "Mount Veeder"), ("O'Shaughnessy", "Howell Mountain"),
    ("Ladera", "Howell Mountain"), ("Robert Craig", "Howell Mountain"),
    ("Storybook Mountain", "Calistoga"), ("Larkmead", "Calistoga"),
    ("Tamber Bey", "Calistoga"), ("Clos Pegase", "Calistoga"),
    ("Sterling Vineyards", "Calistoga"), ("Domaine Chandon", "Yountville"),
    ("Goosecross", "Yountville"), ("Bell Wine Cellars", "Yountville"),
    ("Silver Trident", "Yountville"), ("Groth", "Oakville"),
    ("Rudd", "Oakville"), ("Screaming Eagle Winery", "Oakville"),
    ("Turnbull", "Oakville"), ("Miner Family", "Oakville"),
    ("Napa Cellars", "Napa Valley"), ("Franciscan", "Napa Valley"),
    ("Markham", "Napa Valley"), ("St. Supery", "Rutherford"),
    ("Whitehall Lane", "Rutherford"), ("Flora Springs", "St. Helena"),
    ("Hall Wines", "St. Helena"), ("Duckhorn Napa", "Napa Valley"),
    ("Beaulieu Vineyard", "Rutherford"), ("Raymond Vineyards", "St. Helena"),
    ("Prisoner Wine Company", "Napa Valley"), ("Orin Swift", "Napa Valley"),
    ("Faust", "Napa Valley"), ("Trinchero", "Napa Valley"),
    ("Silverado Trail", "Napa Valley"), ("Frank Family", "Calistoga"),
    ("Chateau Boswell", "St. Helena"), ("Del Dotto", "Napa Valley"),
    ("Grieve Family", "Napa Valley"), ("Anomaly", "St. Helena"),
    # -- Sonoma / Mendocino --
    ("Ramey Wine Cellars", "Russian River Valley"), ("Paul Hobbs", "Russian River Valley"),
    ("DuMOL", "Russian River Valley"), ("Dutton-Goldfield", "Russian River Valley"),
    ("Lynmar Estate", "Russian River Valley"), ("Emeritus", "Russian River Valley"),
    ("Siduri", "Russian River Valley"), ("Papapietro Perry", "Russian River Valley"),
    ("J Vineyards", "Russian River Valley"), ("Balletto", "Russian River Valley"),
    ("MacRostie", "Russian River Valley"), ("Joseph Swan Vineyards", "Russian River Valley"),
    ("Dehlinger Winery", "Russian River Valley"), ("Marcassin", "Sonoma Coast"),
    ("Peay Vineyards", "Sonoma Coast"), ("Failla", "Sonoma Coast"),
    ("Freeman", "Sonoma Coast"), ("Red Car", "Sonoma Coast"),
    ("Occidental", "Sonoma Coast"), ("Sojourn Cellars", "Sonoma Coast"),
    ("Three Sticks", "Sonoma Coast"), ("Patz & Hall", "Sonoma Coast"),
    ("Ridge Lytton Springs", "Dry Creek Valley"), ("Quivira", "Dry Creek Valley"),
    ("A. Rafanelli", "Dry Creek Valley"), ("Mauritson", "Dry Creek Valley"),
    ("Bella Vineyards", "Dry Creek Valley"), ("Truett-Hurst", "Dry Creek Valley"),
    ("Silver Oak Alexander Valley", "Alexander Valley"), ("Stonestreet", "Alexander Valley"),
    ("Simi", "Alexander Valley"), ("Robert Young Estate", "Alexander Valley"),
    ("Ferrari-Carano", "Dry Creek Valley"), ("Chateau St. Jean", "Sonoma County"),
    ("Benziger", "Sonoma County"), ("Kunde", "Sonoma County"),
    ("St. Francis", "Sonoma County"), ("Gundlach Bundschu", "Sonoma County"),
    ("Buena Vista", "Sonoma County"), ("Hanzell", "Sonoma County"),
    ("Laurel Glen", "Sonoma County"), ("Arrowood", "Sonoma County"),
    ("Matanzas Creek", "Sonoma County"), ("Jordan", "Alexander Valley"),
    ("Rombauer Vineyards Carneros", "Carneros"), ("Sonoma-Cutrer", "Russian River Valley"),
    ("Roederer Estate", "Anderson Valley"), ("Navarro Vineyards", "Anderson Valley"),
    ("Goldeneye", "Anderson Valley"), ("Handley Cellars", "Anderson Valley"),
    ("Copain", "Anderson Valley"), ("Drew Family", "Anderson Valley"),
    # -- Central Coast & other US --
    ("Ridge Monte Bello", "Santa Cruz Mountains"), ("Rhys Vineyards", "Santa Cruz Mountains"),
    ("Thomas Fogarty", "Santa Cruz Mountains"), ("Testarossa", "Santa Cruz Mountains"),
    ("Bien Nacido", "Santa Barbara County"), ("Foxen", "Santa Barbara County"),
    ("Zaca Mesa", "Santa Barbara County"), ("Fess Parker", "Santa Barbara County"),
    ("Melville", "Sta. Rita Hills"), ("Brewer-Clifton", "Sta. Rita Hills"),
    ("Hilliard Bruce", "Sta. Rita Hills"), ("Liquid Farm", "Sta. Rita Hills"),
    ("Lucia", "Santa Lucia Highlands"), ("Pisoni", "Santa Lucia Highlands"),
    ("Hahn", "Santa Lucia Highlands"), ("Morgan", "Santa Lucia Highlands"),
    ("Booker", "Willow Creek District"), ("Denner", "Willow Creek District"),
    ("L'Aventure", "Willow Creek District"), ("Daou", "Adelaida District"),
    ("Halter Ranch", "Adelaida District"), ("Epoch Estate", "Willow Creek District"),
    ("Ridge Paso", "Paso Robles"), ("Eberle", "Paso Robles"),
    ("Wild Horse", "Paso Robles"), ("Sextant", "Paso Robles"),
    ("Chamisal", "Edna Valley"), ("Center of Effort", "Edna Valley"),
    ("Domaine Serene", "Dundee Hills"), ("Archery Summit", "Dundee Hills"),
    ("Sokol Blosser", "Dundee Hills"), ("Erath", "Dundee Hills"),
    ("The Eyrie Vineyards", "Dundee Hills"), ("Adelsheim", "Willamette Valley"),
    ("King Estate", "Willamette Valley"), ("Willamette Valley Vineyards", "Willamette Valley"),
    ("Elk Cove", "Willamette Valley"), ("Rex Hill", "Willamette Valley"),
    ("Evening Land", "Willamette Valley"), ("Antica Terra", "Willamette Valley"),
    ("Columbia Crest", "Columbia Valley"), ("Charles Smith", "Columbia Valley"),
    ("K Vintners", "Walla Walla Valley"), ("Andrew Will", "Columbia Valley"),
    ("DeLille Cellars", "Columbia Valley"), ("Betz Family", "Columbia Valley"),
    ("Woodward Canyon", "Walla Walla Valley"), ("Reynvaan", "Walla Walla Valley"),
    ("Gramercy Cellars", "Walla Walla Valley"), ("Col Solare", "Red Mountain"),
    ("Hedges", "Red Mountain"), ("Ravenswood Lodi", "Sonoma County"),
    ("Ravines", "Finger Lakes"), ("Ravenswood Winery", "Sonoma County"),
    # -- France --
    ("Chateau Giscours", "Margaux"), ("Chateau Brane-Cantenac", "Margaux"),
    ("Chateau Rauzan-Segla", "Margaux"), ("Chateau d'Issan", "Margaux"),
    ("Chateau Duhart-Milon", "Pauillac"), ("Chateau d'Armailhac", "Pauillac"),
    ("Chateau Clerc Milon", "Pauillac"), ("Chateau Batailley", "Pauillac"),
    ("Chateau Haut-Batailley", "Pauillac"), ("Chateau Lagrange", "Saint-Julien"),
    ("Chateau Langoa Barton", "Saint-Julien"), ("Chateau Branaire-Ducru", "Saint-Julien"),
    ("Chateau Lafon-Rochet", "Saint-Estephe"), ("Chateau Phelan Segur", "Saint-Estephe"),
    ("Chateau Ormes de Pez", "Saint-Estephe"), ("Chateau Sociando-Mallet", "Haut-Medoc"),
    ("Chateau Chasse-Spleen", "Haut-Medoc"), ("Chateau Poujeaux", "Haut-Medoc"),
    ("Chateau Cantemerle", "Haut-Medoc"), ("Chateau La Lagune", "Haut-Medoc"),
    ("Chateau Pape Clement", "Pessac-Leognan"), ("Chateau Haut-Bailly", "Pessac-Leognan"),
    ("Chateau Carbonnieux", "Pessac-Leognan"), ("Chateau Malartic-Lagraviere", "Pessac-Leognan"),
    ("Chateau La Conseillante", "Pomerol"), ("Chateau L'Evangile", "Pomerol"),
    ("Chateau Clinet", "Pomerol"), ("Chateau Gazin", "Pomerol"),
    ("Chateau Nenin", "Pomerol"), ("Chateau Beausejour", "Saint-Emilion"),
    ("Chateau Canon", "Saint-Emilion"), ("Chateau Troplong Mondot", "Saint-Emilion"),
    ("Chateau Valandraud", "Saint-Emilion"), ("Chateau Pavie-Macquin", "Saint-Emilion"),
    ("Chateau Rieussec", "Sauternes"), ("Chateau Coutet", "Sauternes"),
    ("Chateau Guiraud", "Sauternes"), ("Chateau La Tour Blanche", "Sauternes"),
    ("Domaine Anne Gros", "Vosne-Romanee"), ("Domaine Emmanuel Rouget", "Vosne-Romanee"),
    ("Domaine Jean Grivot", "Vosne-Romanee"), ("Domaine Mugneret-Gibourg", "Vosne-Romanee"),
    ("Domaine Fourrier", "Gevrey-Chambertin"), ("Domaine Denis Mortet", "Gevrey-Chambertin"),
    ("Domaine Claude Dugat", "Gevrey-Chambertin"), ("Domaine Trapet", "Gevrey-Chambertin"),
    ("Domaine Hudelot-Noellat", "Chambolle-Musigny"), ("Domaine Jacques-Frederic Mugnier", "Chambolle-Musigny"),
    ("Domaine Clos de Tart", "Morey-Saint-Denis"), ("Domaine des Lambrays", "Morey-Saint-Denis"),
    ("Domaine Henri Gouges", "Nuits-Saint-Georges"), ("Domaine Robert Chevillon", "Nuits-Saint-Georges"),
    ("Domaine Michel Lafarge", "Volnay"), ("Domaine de Montille", "Volnay"),
    ("Domaine Comte Armand", "Pommard"), ("Domaine Roulot", "Meursault"),
    ("Domaine Arnaud Ente", "Meursault"), ("Domaine Pierre-Yves Colin-Morey", "Chassagne-Montrachet"),
    ("Domaine Bernard Moreau", "Chassagne-Montrachet"), ("Domaine Etienne Sauzet", "Puligny-Montrachet"),
    ("Domaine Long-Depaquit", "Chablis"), ("Domaine Christian Moreau", "Chablis"),
    ("Domaine Billaud-Simon", "Chablis"), ("Domaine Laroche", "Chablis"),
    ("Domaine Jean-Marc Boillot", "Puligny-Montrachet"), ("Maison Joseph Faiveley", "Nuits-Saint-Georges"),
    ("Domaine Marcel Lapierre", "Morgon"), ("Domaine Jean Foillard", "Morgon"),
    ("Chateau Thivin", "Beaujolais"), ("Georges Duboeuf", "Beaujolais"),
    ("Delas Freres", "Hermitage"), ("Domaine Jean-Luc Colombo", "Cornas"),
    ("Domaine Alain Voge", "Cornas"), ("Yves Cuilleron", "Condrieu"),
    ("Georges Vernay", "Condrieu"), ("Domaine Jamet", "Cote-Rotie"),
    ("Domaine Ogier", "Cote-Rotie"), ("Chateau La Nerthe", "Chateauneuf-du-Pape"),
    ("Domaine de la Janasse", "Chateauneuf-du-Pape"), ("Domaine Charvin", "Chateauneuf-du-Pape"),
    ("Domaine Bosquet des Papes", "Chateauneuf-du-Pape"), ("Chateau de Saint Cosme", "Gigondas"),
    ("Domaine Santa Duc", "Gigondas"), ("Perrin et Fils", "Cotes du Rhone"),
    ("Guigal Cotes du Rhone", "Cotes du Rhone"), ("Domaine Alain Graillot", "Crozes-Hermitage"),
    ("Domaine Lucien Crochet", "Sancerre"), ("Domaine Francois Cotat", "Sancerre"),
    ("Domaine Alphonse Mellot", "Sancerre"), ("Domaine Bernard Baudry", "Chinon"),
    ("Charles Joguet", "Chinon"), ("Domaine Philippe Foreau", "Vouvray"),
    ("Domaine des Baumard", "Savennieres"), ("Domaine Ostertag", "Alsace"),
    ("Domaine Marcel Deiss", "Alsace"), ("Josmeyer", "Alsace"),
    ("Domaine Schlumberger", "Alsace"), ("Domaine Ott", "Cotes de Provence"),
    ("Chateau d'Esclans", "Cotes de Provence"), ("Chateau Miraval", "Cotes de Provence"),
    ("Domaine Pibarnon", "Bandol"), ("Chateau de Pibarnon", "Bandol"),
    ("Deutz", "Champagne"), ("Henriot", "Champagne"), ("Ayala", "Champagne"),
    ("Nicolas Feuillatte", "Champagne"), ("Lanson", "Champagne"),
    ("Mumm", "Champagne"), ("Bruno Paillard", "Champagne"),
    ("Larmandier-Bernier", "Champagne"), ("Pierre Peters", "Champagne"),
    ("Agrapart", "Champagne"), ("Chartogne-Taillet", "Champagne"),
    ("Marie-Courtin", "Champagne"), ("Cedric Bouchard", "Champagne"),
    # -- Italy / Spain / Portugal / Germany / Austria --
    ("Roberto Voerzio", "Barolo"), ("Luciano Sandrone", "Barolo"),
    ("Domenico Clerico", "Barolo"), ("Aldo Conterno", "Barolo"),
    ("Conterno Fantino", "Barolo"), ("Fontanafredda", "Barolo"),
    ("Cavallotto", "Barolo"), ("Brovia", "Barolo"), ("Oddero", "Barolo"),
    ("Francesco Rinaldi", "Barolo"), ("Giuseppe Rinaldi", "Barolo"),
    ("Ceretto", "Barbaresco"), ("Marchesi di Gresy", "Barbaresco"),
    ("Sottimano", "Barbaresco"), ("Albino Rocca", "Barbaresco"),
    ("Vietti Barbera", "Barbera d'Alba"), ("Braida", "Barbera d'Asti"),
    ("Badia a Coltibuono", "Chianti Classico"), ("Querciabella", "Chianti Classico"),
    ("San Felice", "Chianti Classico"), ("Volpaia", "Chianti Classico"),
    ("Rocca delle Macie", "Chianti Classico"), ("Nozzole", "Chianti Classico"),
    ("Frescobaldi", "Chianti Classico"), ("Castello di Fonterutoli", "Chianti Classico"),
    ("Poggio di Sotto", "Brunello di Montalcino"), ("Valdicava", "Brunello di Montalcino"),
    ("Cerbaiona", "Brunello di Montalcino"), ("Fuligni", "Brunello di Montalcino"),
    ("Altesino", "Brunello di Montalcino"), ("Argiano", "Brunello di Montalcino"),
    ("Sassicaia", "Bolgheri"), ("Guado al Tasso", "Bolgheri"),
    ("Grattamacco", "Bolgheri"), ("Michele Satta", "Bolgheri"),
    ("Bertani", "Amarone della Valpolicella"), ("Tommasi", "Amarone della Valpolicella"),
    ("Zenato", "Amarone della Valpolicella"), ("Pieropan", "Soave"),
    ("Inama", "Soave"), ("Nino Franco", "Prosecco"), ("Bisol", "Prosecco"),
    ("Ferrari", "Franciacorta"), ("Terlano", "Alto Adige"),
    ("Elena Walch", "Alto Adige"), ("Tramin", "Alto Adige"),
    ("Livio Felluga", "Friuli"), ("Gravner", "Friuli"), ("Radikon", "Friuli"),
    ("Tenuta delle Terre Nere", "Etna"), ("Frank Cornelissen", "Etna"),
    ("Donnafugata", "Sicilia"), ("Tasca d'Almerita", "Sicilia"),
    ("Mastroberardino", "Taurasi"), ("Feudi di San Gregorio", "Taurasi"),
    ("Bodegas Roda", "Rioja"), ("Contino", "Rioja"), ("Sierra Cantabria", "Rioja"),
    ("Bodegas Bilbainas", "Rioja"), ("Faustino", "Rioja"), ("Campo Viejo", "Rioja"),
    ("Beronia", "Rioja"), ("Bodegas Lan", "Rioja"), ("Ramon Bilbao", "Rioja"),
    ("Aalto", "Ribera del Duero"), ("Bodegas Portia", "Ribera del Duero"),
    ("Protos", "Ribera del Duero"), ("Abadia Retuerta", "Ribera del Duero"),
    ("Clos Erasmus", "Priorat"), ("Mas Doix", "Priorat"), ("Terroir al Limit", "Priorat"),
    ("Martin Codax", "Rias Baixas"), ("Bodegas Terras Gauda", "Rias Baixas"),
    ("Jose Pariente", "Rueda"), ("Numanthia", "Toro"),
    ("Freixenet", "Cava"), ("Codorniu", "Cava"), ("Gramona", "Cava"),
    ("Recaredo", "Cava"), ("Barbadillo", "Jerez"), ("Valdespino", "Jerez"),
    ("Croft", "Porto"), ("Sandeman", "Porto"), ("Ramos Pinto", "Porto"),
    ("Quinta do Vesuvio", "Porto"), ("Quinta do Vale Meao", "Douro"),
    ("Wine & Soul", "Douro"), ("Casa Ferreirinha", "Douro"),
    ("Henriques & Henriques", "Madeira"), ("Broadbent", "Madeira"),
    ("Fritz Haag", "Mosel"), ("Von Schubert", "Mosel"), ("Karthauserhof", "Mosel"),
    ("Weingut Clemens Busch", "Mosel"), ("Zilliken", "Mosel"),
    ("Kunstler", "Rheingau"), ("Leitz", "Rheingau"), ("Peter Jakob Kuhn", "Rheingau"),
    ("Gunderloch", "Rheinhessen"), ("Battenfeld-Spanier", "Rheinhessen"),
    ("Schafer-Frohlich", "Nahe"), ("Von Winning", "Pfalz"),
    ("Bassermann-Jordan", "Pfalz"), ("Christmann", "Pfalz"),
    ("Bernhard Huber", "Baden"), ("Nigl", "Kamptal"), ("Hirsch", "Kamptal"),
    ("Alzinger", "Wachau"), ("Veyder-Malberg", "Wachau"),
    ("Umathum", "Burgenland"), ("Kracher", "Burgenland"),
    # -- Southern hemisphere --
    ("Wolf Blass", "Barossa Valley"), ("Seppeltsfield", "Barossa Valley"),
    ("Rockford", "Barossa Valley"), ("St Hallett", "Barossa Valley"),
    ("Two Hands", "Barossa Valley"), ("Standish", "Barossa Valley"),
    ("Kaesler", "Barossa Valley"), ("Charles Melton", "Barossa Valley"),
    ("Chateau Tanunda", "Barossa Valley"), ("Elderton", "Barossa Valley"),
    ("Clarendon Hills", "McLaren Vale"), ("Wirra Wirra", "McLaren Vale"),
    ("Chapel Hill", "McLaren Vale"), ("Yangarra", "McLaren Vale"),
    ("Mollydooker", "McLaren Vale"), ("Kilikanoon", "Clare Valley"),
    ("Pikes", "Clare Valley"), ("Mount Horrocks", "Clare Valley"),
    ("Pewsey Vale", "Eden Valley"), ("Katnook", "Coonawarra"),
    ("Majella", "Coonawarra"), ("Balnaves", "Coonawarra"),
    ("Xanadu", "Margaret River"), ("Pierro", "Margaret River"),
    ("Voyager Estate", "Margaret River"), ("Woodlands", "Margaret River"),
    ("Yarra Yering", "Yarra Valley"), ("Yeringberg", "Yarra Valley"),
    ("De Bortoli", "Yarra Valley"), ("Brokenwood", "Hunter Valley"),
    ("Mount Pleasant", "Hunter Valley"), ("Astrolabe", "Marlborough"),
    ("Seresin", "Marlborough"), ("Nautilus", "Marlborough"),
    ("Saint Clair", "Marlborough"), ("Whitehaven", "Marlborough"),
    ("Brancott Estate", "Marlborough"), ("Jackson Estate", "Marlborough"),
    ("Mount Difficulty", "Central Otago"), ("Two Paddocks", "Central Otago"),
    ("Burn Cottage", "Central Otago"), ("Quartz Reef", "Central Otago"),
    ("Te Mata", "Hawke's Bay"), ("Trinity Hill", "Hawke's Bay"),
    ("Bodega Norton", "Mendoza"), ("Terrazas de los Andes", "Mendoza"),
    ("Alta Vista", "Mendoza"), ("Susana Balbo", "Mendoza"),
    ("Bodega Colome", "Mendoza"), ("Salentein", "Uco Valley"),
    ("Vina Cobos", "Mendoza"), ("Luigi Bosca", "Mendoza"),
    ("Don Melchor", "Maipo Valley"), ("Santa Rita", "Maipo Valley"),
    ("Vina Carmen", "Maipo Valley"), ("Undurraga", "Maipo Valley"),
    ("Vik", "Colchagua Valley"), ("Clos Apalta", "Colchagua Valley"),
    ("Vina Seña", "Colchagua Valley"), ("Cousino-Macul", "Maipo Valley"),
    ("Boekenhoutskloof", "Stellenbosch"), ("Vilafonte", "Stellenbosch"),
    ("Thelema", "Stellenbosch"), ("Warwick Estate", "Stellenbosch"),
    ("Delaire Graff", "Stellenbosch"), ("Mullineux", "Swartland"),
    ("A.A. Badenhorst", "Swartland"), ("Porseleinberg", "Swartland"),
]

# fmt: on

# Alternate names that should resolve to a canonical appellation. Wine names
# vary by label, by country, and by how much of the official name people use.
ALIASES: dict[str, str] = {
    "Los Carneros": "Carneros",
    "Carneros District": "Carneros",
    "Cotes-du-Rhone": "Cotes du Rhone",
    "Chateauneuf du Pape": "Chateauneuf-du-Pape",
    "Chateauneuf-du-pape": "Chateauneuf-du-Pape",
    "Cote Rotie": "Cote-Rotie",
    "St-Julien": "Saint-Julien", "St. Julien": "Saint-Julien", "St Julien": "Saint-Julien",
    "St-Estephe": "Saint-Estephe", "St. Estephe": "Saint-Estephe", "St Estephe": "Saint-Estephe",
    "St-Emilion": "Saint-Emilion", "St. Emilion": "Saint-Emilion", "St Emilion": "Saint-Emilion",
    "St-Joseph": "Saint-Joseph", "St. Joseph": "Saint-Joseph",
    "Saint Helena": "St. Helena", "St Helena": "St. Helena",
    "Stags Leap": "Stags Leap District", "Stag's Leap District": "Stags Leap District",
    "Santa Rita Hills": "Sta. Rita Hills", "Sta Rita Hills": "Sta. Rita Hills",
    "Napa": "Napa Valley",
    "Cote de Nuits": "Nuits-Saint-Georges",
    "Puligny Montrachet": "Puligny-Montrachet",
    "Chassagne Montrachet": "Chassagne-Montrachet",
    "Gevrey Chambertin": "Gevrey-Chambertin",
    "Chambolle Musigny": "Chambolle-Musigny",
    "Vosne Romanee": "Vosne-Romanee",
    "Morey Saint Denis": "Morey-Saint-Denis", "Morey-St-Denis": "Morey-Saint-Denis",
    "Nuits Saint Georges": "Nuits-Saint-Georges", "Nuits-St-Georges": "Nuits-Saint-Georges",
    "Rioja Alta": "Rioja", "Rioja Alavesa": "Rioja",
    "Port": "Porto", "Oporto": "Porto",
    "Sherry": "Jerez", "Jerez-Xeres-Sherry": "Jerez",
    "Mosel-Saar-Ruwer": "Mosel",
    "Montalcino": "Brunello di Montalcino",
    "Valpolicella Classico": "Valpolicella",
    "Amarone": "Amarone della Valpolicella",
    "Etna Rosso": "Etna", "Etna Bianco": "Etna",
    "Barbera": "Barbera d'Alba", "Dolcetto": "Dolcetto d'Alba",
    "Willamette": "Willamette Valley",
    "Russian River": "Russian River Valley",
    "Dry Creek": "Dry Creek Valley",
    "Alexander Valley AVA": "Alexander Valley",
    "Columbia Valley AVA": "Columbia Valley",
    "Walla Walla": "Walla Walla Valley",
    "Barossa": "Barossa Valley",
    "Hawkes Bay": "Hawke's Bay",
    "Maipo": "Maipo Valley", "Colchagua": "Colchagua Valley",
    "Casablanca": "Casablanca Valley",
    "Uco": "Uco Valley",
    "Provence": "Cotes de Provence",
    "Cotes de Nuits": "Nuits-Saint-Georges",
}

# Cuvées for houses whose range people actually choose between. Offline this
# powers the "which bottling?" picker; with a backend the model supplies more.
BOTTLINGS: dict[str, list[tuple[str, str]]] = {
    "Chateau Margaux": [("Grand Vin", "The first wine."),
                        ("Pavillon Rouge", "Second wine."),
                        ("Pavillon Blanc", "Sauvignon Blanc.")],
    "Ridge Vineyards": [("Monte Bello", "The flagship Cabernet."),
                        ("Lytton Springs", "Zinfandel blend, Dry Creek."),
                        ("Geyserville", "Zinfandel blend, Alexander Valley."),
                        ("Estate Cabernet Sauvignon", "Santa Cruz Mountains estate.")],
    "Giacomo Conterno": [("Barolo Cascina Francia", "Estate Barolo."),
                         ("Barolo Monfortino Riserva", "The long-aged riserva."),
                         ("Barbera d'Alba Cascina Francia", "Estate Barbera.")],
    "Caymus Vineyards": [("Napa Valley Cabernet Sauvignon", "The core bottling."),
                         ("Special Selection", "Reserve Cabernet.")],
    "Penfolds": [("Grange", "The flagship Shiraz."), ("Bin 707", "Cabernet Sauvignon."),
                 ("St Henri", "Shiraz, no new oak."), ("Bin 389", "Cabernet Shiraz.")],
    "Krug": [("Grande Cuvee", "The multi-vintage blend."), ("Rose", "The rosé bottling."),
             ("Clos du Mesnil", "Single-vineyard Blanc de Blancs.")],
    "Dr. Loosen": [("Wehlener Sonnenuhr Riesling Kabinett", "Classic off-dry Kabinett."),
                   ("Urziger Wurzgarten Riesling Spatlese", "Red-slate site, spicier."),
                   ("Blue Slate Riesling Kabinett", "Estate entry Riesling.")],
    "Cloudy Bay": [("Sauvignon Blanc", "The Marlborough benchmark."),
                   ("Te Koko", "Barrel-fermented Sauvignon."), ("Chardonnay", "Estate Chardonnay.")],
    "Opus One": [("Opus One", "The single grand vin."), ("Overture", "Non-vintage second wine.")],
    "Silver Oak": [("Alexander Valley Cabernet Sauvignon", "The Sonoma bottling."),
                   ("Napa Valley Cabernet Sauvignon", "The Napa bottling.")],
    "Duckhorn Vineyards": [("Napa Valley Merlot", "The signature Merlot."),
                           ("Three Palms Vineyard Merlot", "Single-vineyard Merlot."),
                           ("Napa Valley Cabernet Sauvignon", "Estate Cabernet.")],
    "Bodegas Muga": [("Reserva", "The classic Rioja Reserva."),
                     ("Prado Enea Gran Reserva", "Long-aged Gran Reserva."),
                     ("Torre Muga", "Modern-styled cuvée.")],
    "Vega Sicilia": [("Unico", "The flagship."), ("Valbuena 5", "Younger release.")],
    "Antinori": [("Tignanello", "The Super Tuscan."), ("Solaia", "Cabernet-led Super Tuscan."),
                 ("Peppoli Chianti Classico", "Estate Chianti.")],
    "Gaja": [("Barbaresco", "The classic Barbaresco."), ("Sori Tildin", "Single vineyard."),
             ("Costa Russi", "Single vineyard."), ("Sperss", "Barolo-sourced.")],
    "Tenuta San Guido": [("Sassicaia", "The original Super Tuscan."),
                         ("Guidalberto", "Second wine."), ("Le Difese", "Entry bottling.")],
    "E. Guigal": [("Chateau d'Ampuis", "Cote-Rotie cuvee."), ("La Mouline", "La La single vineyard."),
                  ("La Turque", "La La single vineyard."), ("La Landonne", "La La single vineyard.")],
    "Chateau de Beaucastel": [("Chateauneuf-du-Pape", "The estate red."),
                              ("Hommage a Jacques Perrin", "Mourvedre-led tete de cuvee."),
                              ("Chateauneuf-du-Pape Blanc", "The white.")],
    "Domaine Leflaive": [("Puligny-Montrachet", "Village white."),
                         ("Les Pucelles", "1er Cru."), ("Chevalier-Montrachet", "Grand Cru.")],
    "Quinta do Noval": [("Vintage Port", "Declared vintage."), ("Nacional", "Ungrafted vines."),
                        ("LBV", "Late bottled vintage.")],
    "Catena Zapata": [("Malbec Argentino", "Flagship Malbec."),
                      ("Nicolas Catena Zapata", "Cabernet-Malbec."), ("Alta Malbec", "Estate Malbec.")],
    "Chateau Musar": [("Red", "The Bekaa red."), ("White", "Obaideh and Merwah."),
                      ("Jeune", "Younger, unoaked range.")],
    "Henschke": [("Hill of Grace", "Old-vine Shiraz."), ("Mount Edelstone", "Single-vineyard Shiraz.")],
    "Felton Road": [("Bannockburn Pinot Noir", "Estate blend."), ("Block 3 Pinot Noir", "Single block."),
                    ("Block 5 Pinot Noir", "Single block.")],
    "Venge Vineyards": [("Scout's Honor", "Proprietary red blend."),
                        ("Silencieux Cabernet Sauvignon", "Napa Valley Cabernet."),
                        ("Bone Ash Cabernet Sauvignon", "Estate Cabernet."),
                        ("Family Reserve Cabernet Sauvignon", "Top Cabernet bottling.")],
    "Orin Swift": [("Papillon", "Bordeaux blend."), ("Abstract", "Grenache-led red."),
                   ("Machete", "Syrah-led red."), ("Mercury Head", "Napa Cabernet.")],
    "Chateau Ste. Michelle": [("Columbia Valley Riesling", "The volume Riesling."),
                              ("Indian Wells Cabernet Sauvignon", "Warm-site Cabernet."),
                              ("Cold Creek Vineyard Cabernet", "Single vineyard.")],
}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Words that carry no identifying weight when matching a producer name.
NOISE = {
    "chateau", "domaine", "bodega", "bodegas", "weingut", "tenuta", "castello",
    "quinta", "winery", "wineries", "vineyard", "vineyards", "cellars", "cellar",
    "estate", "estates", "wines", "wine", "the", "and", "et", "di", "de", "del",
    "della", "du", "des", "la", "le", "el", "y", "cie", "co", "company", "family",
}


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _WS.sub(" ", _PUNCT.sub(" ", folded)).strip().lower()


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t and t not in NOISE]


# The repository's two samples disagree with each other on a handful of wines,
# and top_rated_sample.json is the wrong one: it files Ridge's Monte Bello under
# Napa Valley (it is Santa Cruz Mountains) and Shafer's Hillside Select under
# Napa Valley (Stags Leap District is both correct and more precise). Corrected
# here rather than by editing the seed files, which are the user's to curate.
SAMPLE_CORRECTIONS: dict[str, str] = {
    "Ridge Vineyards (Monte Bello)": "Santa Cruz Mountains",
    "Shafer Vineyards (Hillside Select)": "Stags Leap District",
}


def load_repo_producers() -> list[tuple[str, str]]:
    """Producers the repository already ships in its top-rated samples."""
    pairs: list[tuple[str, str]] = []
    for name in ("top_rated_sample.json", "top_rated_california_sample.json"):
        path = DATA / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        for appellation in payload.get("appellations", []):
            for winery in appellation.get("top_wineries", []):
                name = winery.get("name")
                if name:
                    pairs.append((name, SAMPLE_CORRECTIONS.get(name, appellation["name"])))
    return pairs


def build() -> dict:
    appellations = {}
    # California carries most of the dataset's weight, so it lives in its own
    # module; it is folded in here on equal terms with the base table.
    for name, region, country, wine_type, grapes, age in APPELLATIONS + CALIFORNIA_AVAS:
        appellations[normalize(name)] = {
            "name": name, "region": region, "country": country,
            "type": wine_type, "grapes": grapes, "age": list(age),
        }

    # Region and country names resolve too, so "Napa" or "Tuscany" alone still
    # fills the country and a plausible grape set.
    regions: dict[str, dict] = {}
    countries: dict[str, dict] = {}
    for entry in appellations.values():
        regions.setdefault(normalize(entry["region"]), {
            "name": entry["region"], "country": entry["country"],
            "type": entry["type"], "grapes": entry["grapes"], "age": entry["age"],
        })
        countries.setdefault(normalize(entry["country"]), {"name": entry["country"]})

    # Aliases point at canonical appellations; unknown targets are a build error
    # rather than a silent no-op.
    aliases: dict[str, str] = {}
    for alias, canonical in ALIASES.items():
        if normalize(canonical) not in appellations:
            raise SystemExit(f"alias {alias!r} targets unknown appellation {canonical!r}")
        aliases[normalize(alias)] = normalize(canonical)

    def resolve_appellation(name: str) -> str | None:
        key = normalize(name)
        key = aliases.get(key, key)
        return key if key in appellations else None

    producers: dict[str, dict] = {}
    unknown: list[tuple[str, str]] = []
    # Sources disagree occasionally. First-wins is fine, but a silent
    # disagreement is a data bug waiting to be noticed by a user, so collect
    # them and print them on every build.
    conflicts: list[tuple[str, str, str]] = []
    # Curated entries are authoritative; repository samples fill the gaps.
    for producer, appellation in PRODUCERS + CALIFORNIA_PRODUCERS + load_repo_producers():
        key = normalize(producer)
        if key in producers:
            if producers[key]["appellation"] != appellation:
                conflicts.append((producer, producers[key]["appellation"], appellation))
            continue
        resolved = resolve_appellation(appellation)
        if resolved is None:
            unknown.append((producer, appellation))
            continue
        record = {"name": producer, "appellation": appellations[resolved]["name"]}
        cuvees = BOTTLINGS.get(producer)
        if cuvees:
            record["bottlings"] = [{"wine_name": n, "note": note} for n, note in cuvees]
        producers[key] = record

    return {
        "_comment": (
            "Offline wine reference for autofill. Regenerate with "
            "`python -m scripts.build_reference`. Appellation facts drive most of "
            "the form; the producer table maps a name to its appellation."
        ),
        "appellations": appellations,
        "aliases": aliases,
        "regions": regions,
        "countries": countries,
        "producers": producers,
        "noise_words": sorted(NOISE),
        "unmatched_sample_appellations": sorted({a for _, a in unknown}),
        "_conflicts": [
            {"producer": p, "kept": kept, "ignored": ignored} for p, kept, ignored in conflicts
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Report without writing")
    args = parser.parse_args()

    reference = build()
    print(f"appellations: {len(reference['appellations'])}")
    print(f"aliases:      {len(reference['aliases'])}")
    print(f"regions:      {len(reference['regions'])}")
    print(f"countries:    {len(reference['countries'])}")
    print(f"producers:    {len(reference['producers'])}")
    with_cuvees = sum(1 for p in reference["producers"].values() if p.get("bottlings"))
    print(f"  with cuvées: {with_cuvees}")
    missing = [n for n in BOTTLINGS if normalize(n) not in reference["producers"]]
    if missing:
        print("  BOTTLINGS entries with no producer row:", missing)
    if reference["_conflicts"]:
        print(f"\nplacement disagreements ({len(reference['_conflicts'])}) — first entry kept:")
        for row in reference["_conflicts"]:
            print(f"  {row['producer']:28} kept {row['kept']:26} over {row['ignored']}")
    if reference["unmatched_sample_appellations"]:
        print("sample appellations with no curated entry (producers skipped):")
        for name in reference["unmatched_sample_appellations"]:
            print(f"  - {name}")

    if args.check:
        return 0

    payload = json.dumps(reference, indent=1, ensure_ascii=False, sort_keys=True)
    OUT.write_text(payload + "\n")
    WEB_COPY.parent.mkdir(parents=True, exist_ok=True)
    WEB_COPY.write_text(payload + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)} and {WEB_COPY.relative_to(ROOT)} "
          f"({len(payload) // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
