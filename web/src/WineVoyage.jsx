import { useState, useEffect, useRef } from "react";
import { askAI, read, store } from "./api.js";

/* ═══════════ DATA: ATLAS ═══════════ */
const W={countries:[
{id:"FR",name:"France",emoji:"🇫🇷",color:"#993556",regions:[
{id:"bordeaux",name:"Bordeaux",appellations:[
{id:"pauillac",name:"Pauillac",grapes:["Cabernet Sauvignon","Merlot"],style:"First Growth territory — Lafite, Latour, Mouton.",lat:45.20,lng:-0.75},
{id:"margaux",name:"Margaux",grapes:["Cabernet Sauvignon","Merlot","Cabernet Franc"],style:"Most perfumed, feminine Bordeaux — elegance over power",lat:45.04,lng:-0.67},
{id:"pessac-leognan",name:"Pessac-Léognan",grapes:["Cabernet Sauvignon","Merlot","Sauvignon Blanc"],style:"Haut-Brion's home — great reds, Bordeaux's finest dry whites",lat:44.73,lng:-0.63},
{id:"medoc",name:"Médoc / Haut-Médoc",grapes:["Cabernet Sauvignon","Merlot","Cabernet Franc"],style:"Structured, age-worthy reds with cassis and cedar",lat:45.30,lng:-0.88},
{id:"st-emilion",name:"Saint-Émilion",grapes:["Merlot","Cabernet Franc"],style:"Plush, velvety reds from limestone plateau",lat:44.89,lng:-0.16},
{id:"pomerol",name:"Pomerol",grapes:["Merlot","Cabernet Franc"],style:"Opulent, truffle-laced reds — home of Pétrus",lat:44.93,lng:-0.20},
{id:"sauternes",name:"Sauternes",grapes:["Sémillon","Sauvignon Blanc","Muscadelle"],style:"Legendary botrytized dessert wines",lat:44.55,lng:-0.34}]},
{id:"burgundy",name:"Burgundy",appellations:[
{id:"cote-de-nuits",name:"Côte de Nuits",grapes:["Pinot Noir"],style:"Grand Cru Pinot — Gevrey, Vosne-Romanée, Chambolle",lat:47.17,lng:4.97},
{id:"cote-de-beaune",name:"Côte de Beaune",grapes:["Chardonnay","Pinot Noir"],style:"Premier Cru whites from Meursault and Puligny",lat:46.98,lng:4.83},
{id:"chablis",name:"Chablis",grapes:["Chardonnay"],style:"Steely, mineral whites from Kimmeridgian clay",lat:47.82,lng:3.80}]},
{id:"rhone",name:"Rhône Valley",appellations:[
{id:"chateauneuf",name:"Châteauneuf-du-Pape",grapes:["Grenache","Syrah","Mourvèdre"],style:"Garrigue-scented, powerful southern blends",lat:44.06,lng:4.83},
{id:"cote-rotie",name:"Côte-Rôtie",grapes:["Syrah","Viognier"],style:"Perfumed, elegant northern Rhône Syrah",lat:45.49,lng:4.82},
{id:"hermitage",name:"Hermitage",grapes:["Syrah","Marsanne","Roussanne"],style:"Monumental Syrah from the iconic hill",lat:45.07,lng:4.84}]},
{id:"champagne",name:"Champagne",appellations:[
{id:"montagne-reims",name:"Montagne de Reims",grapes:["Pinot Noir","Chardonnay"],style:"Powerful, structured Champagnes",lat:49.16,lng:3.95},
{id:"cote-des-blancs",name:"Côte des Blancs",grapes:["Chardonnay"],style:"Elegant Blanc de Blancs territory",lat:48.95,lng:3.95}]},
{id:"loire",name:"Loire Valley",appellations:[
{id:"sancerre",name:"Sancerre",grapes:["Sauvignon Blanc","Pinot Noir"],style:"Flinty, citrus-driven Sauvignon Blanc",lat:47.33,lng:2.84},
{id:"vouvray",name:"Vouvray",grapes:["Chenin Blanc"],style:"Versatile Chenin — dry to sweet to sparkling",lat:47.42,lng:0.80}]},
{id:"alsace",name:"Alsace",appellations:[
{id:"alsace-main",name:"Alsace AOC",grapes:["Riesling","Gewürztraminer","Pinot Gris"],style:"Aromatic dry whites — Germanic grapes, French finesse",lat:48.15,lng:7.30},
{id:"alsace-gc",name:"Alsace Grand Cru",grapes:["Riesling","Gewürztraminer"],style:"51 named sites — terroir-driven single-vineyard bottlings",lat:48.20,lng:7.32}]},
{id:"provence",name:"Provence",appellations:[
{id:"bandol",name:"Bandol",grapes:["Mourvèdre","Grenache","Cinsault"],style:"Serious Mourvèdre reds and iconic rosé",lat:43.17,lng:5.75}]}]},
{id:"IT",name:"Italy",emoji:"🇮🇹",color:"#D85A30",regions:[
{id:"tuscany",name:"Tuscany",appellations:[
{id:"chianti-classico",name:"Chianti Classico",grapes:["Sangiovese"],style:"Cherry, leather, herb — Tuscany's heartbeat",lat:43.47,lng:11.25},
{id:"brunello",name:"Brunello di Montalcino",grapes:["Sangiovese Grosso"],style:"Majestic, long-lived Sangiovese at its pinnacle",lat:43.06,lng:11.49},
{id:"bolgheri",name:"Bolgheri",grapes:["Cabernet Sauvignon","Merlot","Cabernet Franc"],style:"Super Tuscan country — Sassicaia, Ornellaia",lat:43.23,lng:10.62},
{id:"vino-nobile",name:"Vino Nobile di Montepulciano",grapes:["Sangiovese (Prugnolo Gentile)"],style:"Noble Sangiovese — structured, earthy, age-worthy",lat:43.10,lng:11.79}]},
{id:"piedmont",name:"Piedmont",appellations:[
{id:"barolo",name:"Barolo",grapes:["Nebbiolo"],style:"The King of Wines — tar, roses, power",lat:44.60,lng:7.94},
{id:"barbaresco",name:"Barbaresco",grapes:["Nebbiolo"],style:"Barolo's elegant sibling — silky and aromatic",lat:44.73,lng:8.08},
{id:"moscato-dasti",name:"Moscato d'Asti",grapes:["Moscato Bianco"],style:"Effervescent, low-alcohol sweetness",lat:44.78,lng:8.20}]},
{id:"veneto",name:"Veneto",appellations:[
{id:"valpolicella",name:"Valpolicella / Amarone",grapes:["Corvina","Rondinella","Molinara"],style:"Fresh Valpolicella to intense dried-grape Amarone",lat:45.52,lng:10.90},
{id:"prosecco",name:"Prosecco Superiore",grapes:["Glera"],style:"Bright, festive sparkling from Valdobbiadene",lat:45.90,lng:11.99},
{id:"soave",name:"Soave Classico",grapes:["Garganega","Trebbiano di Soave"],style:"Delicate, almond-scented whites from volcanic soils",lat:45.42,lng:11.25}]},
{id:"sicily",name:"Sicily",appellations:[
{id:"etna",name:"Etna DOC",grapes:["Nerello Mascalese","Carricante"],style:"Volcanic elegance — Burgundy of the Mediterranean",lat:37.75,lng:15.00}]}]},
{id:"ES",name:"Spain",emoji:"🇪🇸",color:"#A32D2D",regions:[
{id:"rioja",name:"Rioja",appellations:[
{id:"rioja-alta",name:"Rioja Alta",grapes:["Tempranillo","Garnacha","Graciano"],style:"Classic balanced Tempranillo with American oak",lat:42.57,lng:-2.73},
{id:"rioja-alavesa",name:"Rioja Alavesa",grapes:["Tempranillo"],style:"Higher altitude, more finesse and structure",lat:42.65,lng:-2.60}]},
{id:"ribera",name:"Ribera del Duero",appellations:[
{id:"ribera-main",name:"Ribera del Duero",grapes:["Tempranillo (Tinto Fino)"],style:"Intense, dark-fruited — Vega Sicilia territory",lat:41.64,lng:-3.70}]},
{id:"priorat",name:"Priorat",appellations:[
{id:"priorat-main",name:"DOQ Priorat",grapes:["Garnacha","Cariñena","Cabernet Sauvignon"],style:"Mineral-driven reds from llicorella slate",lat:41.20,lng:0.75}]},
{id:"rias-baixas",name:"Rías Baixas",appellations:[
{id:"rias-main",name:"Rías Baixas",grapes:["Albariño"],style:"Crisp, saline whites perfect with seafood",lat:42.20,lng:-8.70}]},
{id:"jerez",name:"Jerez",appellations:[
{id:"jerez-main",name:"Jerez-Xérès-Sherry",grapes:["Palomino Fino","Pedro Ximénez"],style:"World's most underrated wines — Fino to PX",lat:36.68,lng:-6.14}]},
{id:"rueda",name:"Rueda",appellations:[
{id:"rueda-main",name:"Rueda DO",grapes:["Verdejo","Sauvignon Blanc"],style:"Aromatic, herbal whites — Spain's Sancerre",lat:41.41,lng:-4.97}]}]},
{id:"US",name:"United States",emoji:"🇺🇸",color:"#534AB7",regions:[
{id:"napa",name:"Napa Valley",appellations:[
{id:"napa-valley",name:"Napa Valley (general)",grapes:["Cabernet Sauvignon","Chardonnay","Merlot"],style:"World-class Cabs across 16 sub-AVAs",lat:38.50,lng:-122.35},
{id:"oakville",name:"Oakville",grapes:["Cabernet Sauvignon"],style:"Benchmark Napa Cab — To Kalon, Opus One",lat:38.43,lng:-122.41},
{id:"rutherford",name:"Rutherford",grapes:["Cabernet Sauvignon"],style:"Famous Rutherford Dust — earthy, structured Cab",lat:38.46,lng:-122.42},
{id:"stags-leap",name:"Stags Leap District",grapes:["Cabernet Sauvignon","Merlot"],style:"Judgment of Paris winner — silky, refined Cabernet",lat:38.39,lng:-122.35},
{id:"howell-mtn",name:"Howell Mountain",grapes:["Cabernet Sauvignon","Malbec"],style:"High-elevation intensity above the fog line",lat:38.57,lng:-122.43},
{id:"carneros-n",name:"Los Carneros",grapes:["Pinot Noir","Chardonnay"],style:"Cool, wind-swept — Napa's Pinot gateway",lat:38.25,lng:-122.37}]},
{id:"sonoma",name:"Sonoma County",appellations:[
{id:"russian-river",name:"Russian River Valley",grapes:["Pinot Noir","Chardonnay","Zinfandel"],style:"Fog-cooled, lush Pinot Noir — Sonoma's crown jewel",lat:38.50,lng:-122.85},
{id:"alexander-valley",name:"Alexander Valley",grapes:["Cabernet Sauvignon","Merlot"],style:"Warm, generous Cabs with soft tannins",lat:38.70,lng:-122.85},
{id:"sonoma-coast",name:"Sonoma Coast",grapes:["Pinot Noir","Chardonnay"],style:"Cool-climate elegance on the Pacific edge",lat:38.40,lng:-123.00},
{id:"dry-creek",name:"Dry Creek Valley",grapes:["Zinfandel","Sauvignon Blanc"],style:"Heritage Zinfandel from old-vine benchland",lat:38.65,lng:-122.93}]},
{id:"central-coast",name:"Central Coast",appellations:[
{id:"paso-robles",name:"Paso Robles",grapes:["Rhône varieties","Zinfandel","Cabernet Sauvignon"],style:"Central Coast warmth, bold reds, rising star",lat:35.63,lng:-120.69},
{id:"sta-rita",name:"Sta. Rita Hills",grapes:["Pinot Noir","Chardonnay"],style:"Transverse valley fog-cooled Pinot perfection",lat:34.67,lng:-120.48},
{id:"santa-cruz-mtns",name:"Santa Cruz Mountains",grapes:["Pinot Noir","Cabernet Sauvignon"],style:"Ridge Vineyards country — rugged mountain terroir",lat:37.15,lng:-122.05}]},
{id:"oregon",name:"Oregon",appellations:[
{id:"willamette",name:"Willamette Valley",grapes:["Pinot Noir","Pinot Gris","Chardonnay"],style:"Burgundian soul in the Pacific Northwest",lat:45.08,lng:-123.08},
{id:"dundee-hills",name:"Dundee Hills",grapes:["Pinot Noir"],style:"Red volcanic soil, the original Oregon Pinot",lat:45.28,lng:-123.08},
{id:"eola-amity",name:"Eola-Amity Hills",grapes:["Pinot Noir","Chardonnay"],style:"Van Duzer winds — tense, high-acid Pinot",lat:44.96,lng:-123.18}]},
{id:"washington",name:"Washington",appellations:[
{id:"walla-walla",name:"Walla Walla Valley",grapes:["Cabernet Sauvignon","Syrah","Merlot"],style:"Desert heat, Columbia Valley depth",lat:46.07,lng:-118.33},
{id:"red-mountain",name:"Red Mountain",grapes:["Cabernet Sauvignon","Merlot"],style:"Washington's most concentrated, tannic reds",lat:46.30,lng:-119.43}]}]},
{id:"AR",name:"Argentina",emoji:"🇦🇷",color:"#185FA5",regions:[
{id:"mendoza",name:"Mendoza",appellations:[
{id:"lujan",name:"Luján de Cuyo",grapes:["Malbec","Cabernet Sauvignon"],style:"Old-vine Malbec with Andean structure",lat:-33.03,lng:-68.88},
{id:"uco",name:"Uco Valley",grapes:["Malbec","Cabernet Franc","Chardonnay"],style:"High-altitude elegance — Gualtallary, Altamira",lat:-33.72,lng:-69.17},
{id:"maipu",name:"Maipú",grapes:["Malbec","Bonarda"],style:"Historic heartland — first Mendoza vineyards",lat:-32.98,lng:-68.47}]},
{id:"salta",name:"Salta",appellations:[
{id:"cafayate",name:"Cafayate",grapes:["Torrontés","Malbec"],style:"Extreme altitude aromatics at 5,000+ feet",lat:-26.07,lng:-66.03}]},
{id:"patagonia",name:"Patagonia",appellations:[
{id:"rio-negro",name:"Río Negro",grapes:["Pinot Noir","Malbec","Sémillon"],style:"Wind-swept, cool-climate frontier",lat:-39.03,lng:-67.08}]}]},
{id:"AU",name:"Australia",emoji:"🇦🇺",color:"#854F0B",regions:[
{id:"south-aus",name:"South Australia",appellations:[
{id:"barossa",name:"Barossa Valley",grapes:["Shiraz","Grenache","Cabernet Sauvignon"],style:"Old-vine Shiraz — bold, concentrated, iconic",lat:-34.56,lng:138.95},
{id:"eden-valley",name:"Eden Valley",grapes:["Riesling","Shiraz"],style:"High-altitude Riesling, elegant cooler Shiraz",lat:-34.63,lng:139.05},
{id:"mclaren",name:"McLaren Vale",grapes:["Shiraz","Grenache"],style:"Mediterranean warmth meets coastal influence",lat:-35.22,lng:138.55},
{id:"adelaide-hills",name:"Adelaide Hills",grapes:["Sauvignon Blanc","Chardonnay","Pinot Noir"],style:"Cool-climate whites above Adelaide",lat:-35.02,lng:138.72},
{id:"clare-valley",name:"Clare Valley",grapes:["Riesling","Shiraz"],style:"Lime-juicy Riesling, structured reds from slate",lat:-33.83,lng:138.60}]},
{id:"victoria",name:"Victoria",appellations:[
{id:"yarra",name:"Yarra Valley",grapes:["Pinot Noir","Chardonnay","Shiraz"],style:"Melbourne's backyard — cool-climate Pinot",lat:-37.75,lng:145.50}]},
{id:"west-aus",name:"Western Australia",appellations:[
{id:"margaret",name:"Margaret River",grapes:["Cabernet Sauvignon","Chardonnay"],style:"Bordeaux structure meets coastal freshness",lat:-33.95,lng:115.07}]}]},
{id:"NZ",name:"New Zealand",emoji:"🇳🇿",color:"#1D9E75",regions:[
{id:"marlborough-r",name:"Marlborough",appellations:[
{id:"marlborough-a",name:"Marlborough",grapes:["Sauvignon Blanc","Pinot Noir"],style:"Explosive Sauvignon — gooseberry and grass",lat:-41.52,lng:173.95}]},
{id:"central-otago-r",name:"Central Otago",appellations:[
{id:"central-otago-a",name:"Central Otago",grapes:["Pinot Noir","Riesling"],style:"World's southernmost — cherry-pure Pinot",lat:-45.03,lng:169.20}]},
{id:"hawkes-bay",name:"Hawke's Bay",appellations:[
{id:"hawkes-bay-a",name:"Hawke's Bay",grapes:["Syrah","Cabernet Sauvignon","Chardonnay"],style:"New Zealand's Bordeaux — warm, gravelly",lat:-39.60,lng:176.85}]}]},
{id:"PT",name:"Portugal",emoji:"🇵🇹",color:"#0F6E56",regions:[
{id:"douro",name:"Douro Valley",appellations:[
{id:"douro-main",name:"Douro DOC",grapes:["Touriga Nacional","Tinta Roriz"],style:"Terraced schist — Port and stunning dry reds",lat:41.16,lng:-7.79}]},
{id:"alentejo",name:"Alentejo",appellations:[
{id:"alentejo-main",name:"Alentejo DOC",grapes:["Aragonez","Trincadeira"],style:"Sun-drenched plains, generous ripe reds",lat:38.57,lng:-7.91}]},
{id:"vinho-verde",name:"Vinho Verde",appellations:[
{id:"vv-main",name:"Vinho Verde DOC",grapes:["Alvarinho","Loureiro"],style:"Zippy, effervescent summer whites",lat:41.80,lng:-8.40}]},
{id:"dao",name:"Dão",appellations:[
{id:"dao-main",name:"Dão DOC",grapes:["Touriga Nacional","Encruzado"],style:"Granite-grown elegance — Portugal's Burgundy",lat:40.53,lng:-7.90}]}]},
{id:"DE",name:"Germany",emoji:"🇩🇪",color:"#639922",regions:[
{id:"mosel",name:"Mosel",appellations:[
{id:"mosel-main",name:"Mosel",grapes:["Riesling"],style:"Slate-driven, electric Rieslings",lat:49.92,lng:6.94}]},
{id:"rheingau",name:"Rheingau",appellations:[
{id:"rheingau-main",name:"Rheingau",grapes:["Riesling","Spätburgunder"],style:"Noble Riesling from south-facing Rhine slopes",lat:50.01,lng:8.05}]},
{id:"pfalz",name:"Pfalz",appellations:[
{id:"pfalz-main",name:"Pfalz",grapes:["Riesling","Spätburgunder"],style:"Germany's sunniest — richer, rounder Riesling",lat:49.35,lng:8.15}]}]},
{id:"ZA",name:"South Africa",emoji:"🇿🇦",color:"#BA7517",regions:[
{id:"stellenbosch-r",name:"Stellenbosch",appellations:[
{id:"stellenbosch-a",name:"Stellenbosch",grapes:["Cabernet Sauvignon","Pinotage","Chenin Blanc"],style:"Mountain-ringed, Bordeaux-quality reds",lat:-33.93,lng:18.86}]},
{id:"swartland",name:"Swartland",appellations:[
{id:"swartland-main",name:"Swartland",grapes:["Chenin Blanc","Syrah","Grenache"],style:"Old-vine revolution — natural wine frontier",lat:-33.45,lng:18.55}]},
{id:"franschhoek-r",name:"Franschhoek",appellations:[
{id:"franschhoek-a",name:"Franschhoek Valley",grapes:["Chardonnay","Chenin Blanc","Cabernet Franc"],style:"Huguenot heritage, stunning setting",lat:-33.87,lng:19.12}]}]},
{id:"CL",name:"Chile",emoji:"🇨🇱",color:"#993C1D",regions:[
{id:"maipo",name:"Maipo Valley",appellations:[
{id:"maipo-main",name:"Maipo Valley",grapes:["Cabernet Sauvignon","Carménère"],style:"Chile's Bordeaux — Almaviva, Don Melchor",lat:-33.65,lng:-70.65}]},
{id:"casablanca",name:"Casablanca Valley",appellations:[
{id:"casablanca-main",name:"Casablanca Valley",grapes:["Sauvignon Blanc","Chardonnay","Pinot Noir"],style:"Cool coastal fog, crisp whites",lat:-33.30,lng:-71.40}]},
{id:"colchagua",name:"Colchagua Valley",appellations:[
{id:"colchagua-main",name:"Colchagua Valley",grapes:["Carménère","Cabernet Sauvignon","Syrah"],style:"Chile's Carménère heartland",lat:-34.65,lng:-71.20}]}]},
{id:"GR",name:"Greece",emoji:"🇬🇷",color:"#378ADD",regions:[
{id:"santorini-r",name:"Santorini",appellations:[
{id:"santorini-a",name:"Santorini PDO",grapes:["Assyrtiko","Athiri","Aidani"],style:"Volcanic mineral whites — basket-trained vines",lat:36.40,lng:25.43}]},
{id:"nemea-r",name:"Nemea",appellations:[
{id:"nemea-a",name:"Nemea PDO",grapes:["Agiorgitiko"],style:"Velvety Greek red with dark fruit and spice",lat:37.82,lng:22.66}]}]}]};

const allApps=[];
W.countries.forEach(c=>c.regions.forEach(r=>r.appellations.forEach(a=>{allApps.push({...a,regionName:r.name,regionId:r.id,countryName:c.name,countryEmoji:c.emoji,countryId:c.id,countryColor:c.color});})));

/* ═══════════ DATA: VARIETAL ENCYCLOPEDIA ═══════════ */
const VARIETALS={
"Cabernet Sauvignon":{t:"r",body:5,tan:5,acid:4,notes:"Cassis, cedar, graphite, tobacco",age:"10–30+ yrs",temp:"16–18°C",pair:["Ribeye with béarnaise","Braised short ribs","Aged cheddar"]},
"Merlot":{t:"r",body:4,tan:3,acid:3,notes:"Plum, black cherry, chocolate, bay",age:"5–15 yrs",temp:"15–17°C",pair:["Roast duck","Mushroom risotto","Filet mignon"]},
"Cabernet Franc":{t:"r",body:3,tan:3,acid:4,notes:"Raspberry, bell pepper, violet, pencil shavings",age:"5–20 yrs",temp:"15–17°C",pair:["Herb-roasted lamb","Ratatouille","Goat cheese tart"]},
"Pinot Noir":{t:"r",body:2,tan:2,acid:4,notes:"Cherry, rose, forest floor, spice",age:"5–20 yrs",temp:"13–15°C",pair:["Seared salmon","Duck breast","Mushroom dishes"]},
"Syrah":{t:"r",body:5,tan:4,acid:3,notes:"Blackberry, black pepper, smoked meat, olive",age:"8–25 yrs",temp:"16–18°C",pair:["Grilled lamb chops","Peppercorn steak","Cassoulet"]},
"Grenache":{t:"r",body:4,tan:3,acid:3,notes:"Strawberry, garrigue, white pepper, licorice",age:"5–15 yrs",temp:"15–17°C",pair:["Herb-crusted pork","Paella","Grilled vegetables"]},
"Mourvèdre":{t:"r",body:5,tan:5,acid:3,notes:"Blackberry, game, leather, thyme",age:"10–25 yrs",temp:"16–18°C",pair:["Wild boar ragù","Lamb tagine","Aged gouda"]},
"Sangiovese":{t:"r",body:3,tan:4,acid:5,notes:"Sour cherry, leather, tomato leaf, herbs",age:"5–25 yrs",temp:"16–18°C",pair:["Bistecca fiorentina","Wild boar pasta","Pecorino"]},
"Nebbiolo":{t:"r",body:4,tan:5,acid:5,notes:"Tar, roses, cherry, truffle, anise",age:"10–40 yrs",temp:"16–18°C",pair:["White truffle risotto","Braised beef","Brasato al Barolo"]},
"Nerello Mascalese":{t:"r",body:2,tan:3,acid:4,notes:"Red cherry, volcanic minerality, herbs",age:"5–15 yrs",temp:"14–16°C",pair:["Grilled swordfish","Pasta alla Norma","Roast chicken"]},
"Tempranillo":{t:"r",body:4,tan:4,acid:3,notes:"Cherry, dried fig, dill, leather, vanilla",age:"5–25 yrs",temp:"15–17°C",pair:["Roast lamb","Jamón ibérico","Manchego"]},
"Malbec":{t:"r",body:4,tan:3,acid:3,notes:"Blackberry, plum, violet, cocoa",age:"5–15 yrs",temp:"15–17°C",pair:["Grilled skirt steak","Asado","Empanadas"]},
"Zinfandel":{t:"r",body:4,tan:3,acid:3,notes:"Jammy blackberry, black pepper, brambly spice",age:"3–10 yrs",temp:"15–17°C",pair:["BBQ ribs","Burgers","Spiced sausage"]},
"Touriga Nacional":{t:"r",body:5,tan:4,acid:4,notes:"Blueberry, violet, bergamot, rockrose",age:"8–25 yrs",temp:"16–18°C",pair:["Braised oxtail","Roast pork","Hard sheep cheese"]},
"Carménère":{t:"r",body:4,tan:3,acid:3,notes:"Black plum, green peppercorn, cocoa, paprika",age:"3–10 yrs",temp:"15–17°C",pair:["Grilled flank steak","Roasted peppers","Lentil stew"]},
"Corvina":{t:"r",body:3,tan:3,acid:4,notes:"Sour cherry, almond, dried fruit (Amarone: fig, raisin)",age:"5–20 yrs",temp:"15–17°C",pair:["Risotto all'Amarone","Braised beef cheeks","Aged Asiago"]},
"Agiorgitiko":{t:"r",body:3,tan:3,acid:3,notes:"Dark cherry, plum, sweet spice, herbs",age:"3–12 yrs",temp:"15–17°C",pair:["Lamb kleftiko","Moussaka","Grilled halloumi"]},
"Pinotage":{t:"r",body:4,tan:4,acid:3,notes:"Dark berry, smoke, rooibos, plum",age:"5–15 yrs",temp:"15–17°C",pair:["Braai (BBQ)","Venison","Smoked brisket"]},
"Chardonnay":{t:"w",body:4,tan:1,acid:3,notes:"Apple, citrus → tropical; oak: butter, brioche",age:"3–15 yrs",temp:"10–13°C",pair:["Lobster with butter","Roast chicken","Creamy pasta"]},
"Sauvignon Blanc":{t:"w",body:2,tan:1,acid:5,notes:"Grapefruit, gooseberry, cut grass, flint",age:"1–5 yrs",temp:"8–10°C",pair:["Goat cheese salad","Ceviche","Asparagus dishes"]},
"Riesling":{t:"w",body:2,tan:1,acid:5,notes:"Lime, green apple, jasmine, petrol with age",age:"5–30+ yrs",temp:"8–10°C",pair:["Thai curry","Pork schnitzel","Spicy Sichuan"]},
"Chenin Blanc":{t:"w",body:3,tan:1,acid:5,notes:"Quince, honey, chamomile, wet wool",age:"3–20 yrs",temp:"9–12°C",pair:["Roast pork belly","Sushi","Soft-rind cheese"]},
"Albariño":{t:"w",body:2,tan:1,acid:4,notes:"White peach, citrus zest, saline",age:"1–5 yrs",temp:"8–10°C",pair:["Grilled octopus","Oysters","Fish tacos"]},
"Assyrtiko":{t:"w",body:3,tan:1,acid:5,notes:"Lemon, flint, sea spray, beeswax",age:"3–10 yrs",temp:"9–11°C",pair:["Grilled whole fish","Feta & tomato","Lemon chicken"]},
"Verdejo":{t:"w",body:2,tan:1,acid:4,notes:"Fennel, citrus, bitter almond, fresh herbs",age:"1–4 yrs",temp:"8–10°C",pair:["Garlic shrimp","White asparagus","Tapas"]},
"Glera":{t:"w",body:1,tan:1,acid:4,notes:"Green apple, pear, white flowers (sparkling)",age:"Drink young",temp:"6–8°C",pair:["Aperitivo & prosciutto","Fried calamari","Brunch"]},
"Moscato":{t:"w",body:1,tan:1,acid:3,notes:"Orange blossom, peach, honeysuckle (sweet, frizzante)",age:"Drink young",temp:"6–8°C",pair:["Fruit tarts","Panettone","Spicy Asian"]},
"Viognier":{t:"w",body:4,tan:1,acid:2,notes:"Apricot, honeysuckle, tangerine oil",age:"1–6 yrs",temp:"10–12°C",pair:["Roast chicken with apricot","Crab cakes","Mild curry"]},
"Gewürztraminer":{t:"w",body:4,tan:1,acid:2,notes:"Lychee, rose, ginger, allspice",age:"2–8 yrs",temp:"9–11°C",pair:["Munster cheese","Duck à l'orange","Thai food"]},
"Sémillon":{t:"w",body:3,tan:1,acid:3,notes:"Lemon, lanolin, honey (botrytis: apricot, saffron)",age:"5–25 yrs",temp:"9–12°C",pair:["Roast chicken","Foie gras (Sauternes)","Blue cheese"]},
"Torrontés":{t:"w",body:2,tan:1,acid:3,notes:"Rose, geranium, peach, lemon zest",age:"1–3 yrs",temp:"8–10°C",pair:["Empanadas","Ceviche","Mild Thai"]},
"Garganega":{t:"w",body:2,tan:1,acid:3,notes:"Almond, honeydew, white peach",age:"2–8 yrs",temp:"9–11°C",pair:["Risotto primavera","Grilled sole","Antipasti"]},
"Pinot Gris":{t:"w",body:3,tan:1,acid:3,notes:"Pear, apple, honey, ginger (Alsace: rich)",age:"2–8 yrs",temp:"9–11°C",pair:["Pork tenderloin","Onion tart","Smoked salmon"]}};

const ALIAS={"sangiovese grosso":"Sangiovese","sangiovese (prugnolo gentile)":"Sangiovese","tempranillo (tinto fino)":"Tempranillo","shiraz":"Syrah","spätburgunder":"Pinot Noir","grauburgunder":"Pinot Gris","alvarinho":"Albariño","moscato bianco":"Moscato","tinta roriz":"Tempranillo","aragonez":"Tempranillo","garnacha":"Grenache","palomino fino":null,"pedro ximénez":null};
const normGrape=g=>{const k=g.toLowerCase().trim();if(ALIAS[k]!==undefined)return ALIAS[k];const clean=k.replace(/\s*\(.*\)/,"");if(ALIAS[clean]!==undefined)return ALIAS[clean];const hit=Object.keys(VARIETALS).find(v=>v.toLowerCase()===clean);return hit||null;};

/* ═══════════ DATA: VINTAGE CHARTS 2015–2024 ═══════════ */
const VINTAGES={
napa:{name:"Napa Valley",y:{2015:[4,"Drought-concentrated, small crop, powerful"],2016:[4.5,"Excellent balance and polish"],2017:[3.5,"Heat spikes and fires — variable"],2018:[5,"Cool, long season — benchmark year"],2019:[4.5,"Generous, ripe, consistent"],2020:[2.5,"Glass Fire smoke; many skipped reds"],2021:[4.5,"Tiny drought crop — concentrated, superb"],2022:[3.5,"Labor Day heat dome; picking time key"],2023:[4.5,"Cool, late, fresh — a classic"],2024:[4,"Even season, promising early"]}},
sonoma:{name:"Sonoma",y:{2015:[4,"Small, concentrated crop"],2016:[4.5,"Poised and complete"],2017:[3.5,"October fires — variable"],2018:[4.5,"Long hang time, excellent"],2019:[4.5,"Even, generous, ripe"],2020:[3,"Smoke variable; coastal sites better"],2021:[4.5,"Drought-small and stellar"],2022:[3.5,"Heat event mid-harvest"],2023:[5,"Long cool season — stellar Pinot"],2024:[4,"Solid, balanced season"]}},
"central-coast":{name:"Central Coast",y:{2015:[4,"Tiny yields, intense"],2016:[4.5,"Outstanding across the board"],2017:[4,"Warm, generous"],2018:[4.5,"Cool and refined"],2019:[4.5,"Textbook season"],2020:[3.5,"Less smoke impact than north"],2021:[4.5,"Small, concentrated, superb"],2022:[3.5,"Heat spike September"],2023:[4.5,"Cool, late — excellent freshness"],2024:[4,"Steady, promising"]}},
oregon:{name:"Willamette Valley",y:{2015:[4.5,"Warm, generous, opulent"],2016:[4.5,"Elegant and complete"],2017:[4,"Cooler, classic style"],2018:[4.5,"Ripe yet balanced"],2019:[4,"Harvest rain; elegant wines"],2020:[2.5,"Wildfire smoke — most reds lost"],2021:[4.5,"Heat dome year, surprisingly great"],2022:[4,"Frost-reduced, quality high"],2023:[4.5,"Abundant and balanced"],2024:[4,"Even, promising"]}},
washington:{name:"Washington",y:{2015:[4,"Warm, early, ripe"],2016:[4.5,"Large and excellent"],2017:[4,"Classic, structured"],2018:[4.5,"Even and outstanding"],2019:[4,"Cool October — fresh"],2020:[3.5,"Smoke touched some sites"],2021:[4.5,"Heat dome — tiny, concentrated"],2022:[4,"Cool start, strong finish"],2023:[4.5,"Balanced, plentiful"],2024:[4,"January freeze cut yields"]}},
bordeaux:{name:"Bordeaux",y:{2015:[4.5,"Excellent — Right Bank shines"],2016:[5,"Structured, classic, superb"],2017:[3.5,"April frost losses"],2018:[4.5,"Powerful and ripe"],2019:[4.5,"Brilliant balance and value"],2020:[4.5,"Third of a great trio"],2021:[3,"Cool, mildew — lighter classical"],2022:[5,"Drought-defying, stunning"],2023:[4,"Mildew pressure, heterogeneous"],2024:[3,"Wet, difficult — select carefully"]}},
burgundy:{name:"Burgundy",y:{2015:[5,"Great red vintage"],2016:[4,"Frost-cut but pure"],2017:[4,"Generous, lovely whites"],2018:[4.5,"Ripe and abundant"],2019:[5,"Concentrated, thrilling"],2020:[4.5,"Early pick, great tension"],2021:[3,"Frost devastation — tiny crop"],2022:[4.5,"Generous and balanced"],2023:[4,"Big crop; sorting mattered"],2024:[3,"Frost and mildew — tiny again"]}},
rhone:{name:"Rhône / Provence",y:{2015:[4.5,"Northern Rhône stellar"],2016:[5,"Southern Rhône legendary"],2017:[4,"Warm, concentrated"],2018:[4,"Mildew in south; north strong"],2019:[4.5,"Excellent both zones"],2020:[4,"Fresh, balanced"],2021:[3.5,"Cooler, fresher style"],2022:[4,"Hot but well-managed"],2023:[4,"Solid, generous"],2024:[3.5,"Uneven; select producers"]}},
champagne:{name:"Champagne",y:{2015:[4,"Ripe, structured"],2016:[3.5,"Frost then recovery"],2017:[3,"Frost — scarce"],2018:[4.5,"Sun-drenched, generous"],2019:[4.5,"Concentrated and fine"],2020:[4,"Completes strong trio"],2021:[3,"Frost and mildew — tiny"],2022:[4.5,"Sunny, superb potential"],2023:[4,"Huge crop, good quality"],2024:[3,"Wet, challenging"]}},
loire:{name:"Loire Valley",y:{2015:[4.5,"Excellent across styles"],2016:[3.5,"Frost losses"],2017:[4,"Fine, classic"],2018:[4.5,"Ripe and generous"],2019:[4,"Small but strong"],2020:[4.5,"Early, excellent"],2021:[3,"Frost — tiny crop"],2022:[4.5,"Dry, concentrated"],2023:[4,"Generous, uneven botrytis"],2024:[3,"Wet, difficult"]}},
tuscany:{name:"Tuscany",y:{2015:[5,"Outstanding across the board"],2016:[5,"Benchmark Sangiovese"],2017:[3.5,"Hot and dry"],2018:[4,"Fresher, classic style"],2019:[4.5,"Excellent balance"],2020:[4,"Very good, even"],2021:[4.5,"Powerful, structured Brunello"],2022:[3.5,"Drought stress"],2023:[3.5,"Mildew; careful selection"],2024:[4,"Promising recovery"]}},
piedmont:{name:"Piedmont",y:{2015:[4.5,"Rich, generous Nebbiolo"],2016:[5,"Epic Barolo — perfumed, structured"],2017:[3.5,"Hot, early"],2018:[4,"Approachable, fragrant"],2019:[4.5,"Classic, built to age"],2020:[4,"Elegant, mid-weight"],2021:[4.5,"Excellent, traditional"],2022:[3.5,"Drought year"],2023:[4,"Good; heat spikes"],2024:[4,"Balanced, promising"]}},
veneto:{name:"Veneto",y:{2015:[4.5,"Superb Amarone"],2016:[4.5,"Elegant and complete"],2017:[3.5,"Hot, dry"],2018:[4,"Generous"],2019:[4.5,"Excellent freshness"],2020:[4,"Very good"],2021:[4.5,"Concentrated, fine"],2022:[4,"Warm, well-handled"],2023:[3.5,"Hail and rain zones"],2024:[4,"Solid"]}},
spain:{name:"Spain",y:{2015:[4.5,"Excellent, ripe"],2016:[4.5,"Fresh and fine"],2017:[4,"Frost hit Ribera"],2018:[4,"Cooler, fresher"],2019:[4.5,"Tiny, superb Rioja"],2020:[4,"Balanced"],2021:[4.5,"Excellent structure"],2022:[4,"Drought-concentrated"],2023:[3.5,"Extreme heat"],2024:[4,"Recovering, promising"]}},
germany:{name:"Germany & Alsace",y:{2015:[4.5,"Ripe, racy, superb"],2016:[4,"Classic, fine"],2017:[4,"Frost-cut, concentrated"],2018:[4.5,"Ripe and generous"],2019:[4.5,"Electric acidity, superb"],2020:[4.5,"Precise, early"],2021:[3.5,"Cool, classic; flood year"],2022:[4,"Dry summer, good"],2023:[4,"Generous, balanced"],2024:[3.5,"Frost and rain pockets"]}},
portugal:{name:"Portugal / Douro",y:{2015:[4.5,"Excellent dry reds"],2016:[4.5,"Declared Port year"],2017:[5,"Historic — declared, powerful"],2018:[4,"Fresh, balanced"],2019:[4,"Classic"],2020:[4,"Widely declared"],2021:[4,"Elegant"],2022:[4.5,"Declared; drought-concentrated"],2023:[4,"Very good"],2024:[4,"Promising"]}},
australia:{name:"Australia",y:{2015:[4,"Even, quality year"],2016:[4.5,"Outstanding SA reds"],2017:[4,"Cool, elegant"],2018:[4.5,"Outstanding Barossa"],2019:[4,"Drought — small"],2020:[3.5,"Bushfire smoke in places"],2021:[5,"Cool, pristine — modern great"],2022:[4.5,"Cool, fine"],2023:[4,"Wet, cooler"],2024:[4,"Solid, balanced"]}},
nz:{name:"New Zealand",y:{2015:[4,"Dry, focused"],2016:[4,"Generous"],2017:[3.5,"Wet harvest"],2018:[3.5,"Hot, humid"],2019:[4.5,"Excellent everywhere"],2020:[4.5,"COVID harvest — excellent"],2021:[4.5,"Tiny, concentrated"],2022:[3.5,"Wet, big crop"],2023:[3.5,"Cyclone hit Hawke's Bay"],2024:[4.5,"Dry, superb"]}},
mendoza:{name:"Argentina",y:{2015:[3.5,"Rainy, lighter"],2016:[3.5,"Cool, wet — fresh style"],2017:[4,"Small, concentrated"],2018:[4.5,"Excellent, balanced"],2019:[4.5,"Outstanding"],2020:[4,"Hot, early"],2021:[4.5,"Fresh, precise"],2022:[4,"Very good"],2023:[4,"Frost-cut yields"],2024:[4.5,"Excellent quality"]}},
chile:{name:"Chile",y:{2015:[4.5,"Superb, classic"],2016:[3.5,"Harvest rain"],2017:[4,"Fires and heat; good wines"],2018:[5,"Long, balanced — exceptional"],2019:[4,"Dry, concentrated"],2020:[4,"Early, warm"],2021:[4.5,"Cool, fresh, fine"],2022:[4,"Balanced"],2023:[4,"Very good"],2024:[4,"Solid"]}},
southafrica:{name:"South Africa",y:{2015:[5,"Landmark year"],2016:[4,"Drought, heat"],2017:[4.5,"Drought-concentrated, excellent"],2018:[4,"Dry, small"],2019:[4,"Balanced"],2020:[4.5,"Excellent, fresh"],2021:[4.5,"Cool, slow — outstanding whites"],2022:[4,"Warm, generous"],2023:[4,"Very good"],2024:[4,"Solid"]}}};
const REGION_VINTAGE={bordeaux:"bordeaux",burgundy:"burgundy",rhone:"rhone",champagne:"champagne",loire:"loire",alsace:"germany",provence:"rhone",tuscany:"tuscany",piedmont:"piedmont",veneto:"veneto",rioja:"spain",ribera:"spain",priorat:"spain","rias-baixas":"spain",rueda:"spain",napa:"napa",sonoma:"sonoma","central-coast":"central-coast",oregon:"oregon",washington:"washington",mendoza:"mendoza",salta:"mendoza",patagonia:"mendoza","south-aus":"australia",victoria:"australia","west-aus":"australia","marlborough-r":"nz","central-otago-r":"nz","hawkes-bay":"nz",douro:"portugal",alentejo:"portugal","vinho-verde":"portugal",dao:"portugal",mosel:"germany",rheingau:"germany",pfalz:"germany","stellenbosch-r":"southafrica",swartland:"southafrica","franschhoek-r":"southafrica",maipo:"chile",casablanca:"chile",colchagua:"chile"};

/* ═══════════ HELPERS ═══════════ */
const YR=new Date().getFullYear();
const uid=()=>Date.now()+Math.random().toString(36).slice(2,6);
const fmt$=n=>"$"+Number(n||0).toLocaleString(undefined,{maximumFractionDigits:0});
const vScore=s=>s>=4.5?"#BA7517":s>=4?"#4E7C4E":s>=3.5?"#8A8A4E":s>=3?"#999":"#A65B4B";
const bottleStatus=b=>{if(b.to&&YR>Number(b.to))return"past";if(b.from&&YR<Number(b.from))return"hold";return"now";};
const STATUS={now:{l:"Drink now",c:"#4E7C4E"},hold:{l:"Hold",c:"#BA7517"},past:{l:"Past peak",c:"#A65B4B"}};


/* ═══════════ DESIGN SYSTEM ═══════════ */
const GOLD="#BA7517",WINE="#7A2E3B",CREAM="#FAF7F2",INK="#2A2420",TER="#9A8C7E",HAIR="#E8DFD2",PARCH="#F5EFE6";
const S={
pg:{fontFamily:"'DM Sans',sans-serif",maxWidth:430,margin:"0 auto",padding:"0 12px 96px"},
serif:{fontFamily:"'Cormorant Garamond',serif"},
hdr:{textAlign:"center",padding:"1.15rem 0 0.1rem"},
logo:{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:600,letterSpacing:"0.5px",color:"#2A2420",margin:0},
sub:{fontSize:10,color:"#9A8C7E",letterSpacing:3,textTransform:"uppercase",margin:"3px 0 0"},
nav:{position:"fixed",bottom:0,left:0,right:0,display:"flex",justifyContent:"center",background:"#FFFFFF",borderTop:"0.5px solid #E8DFD2",zIndex:50,backdropFilter:"blur(12px)"},
navIn:{display:"flex",width:"100%",maxWidth:430},
navB:a=>({flex:1,padding:"10px 0 14px",textAlign:"center",background:"none",border:"none",cursor:"pointer",color:a?WINE:"#9A8C7E",transition:"all 0.2s",transform:a?"translateY(-1px)":"none"}),
navI:{fontSize:19,display:"block",marginBottom:2},
navL:a=>({fontSize:9.5,fontWeight:a?600:400,letterSpacing:0.4}),
cd:{background:"#FFFFFF",border:"0.5px solid #E8DFD2",borderRadius:14,padding:"1rem",marginBottom:10,transition:"border-color 0.2s"},
cdT:{background:"#FFFFFF",border:"0.5px solid #E8DFD2",borderRadius:14,padding:"1rem",marginBottom:10,cursor:"pointer"},
bg:c=>({display:"inline-block",padding:"3px 10px",borderRadius:20,fontSize:11,fontWeight:500,background:(c||"#888")+"1A",color:c||"#888",marginRight:5,marginBottom:4}),
pill:c=>({display:"inline-block",padding:"2px 9px",borderRadius:12,fontSize:10.5,fontWeight:600,background:c+"1A",color:c,letterSpacing:0.3}),
inp:{width:"100%",padding:"11px 12px",borderRadius:12,fontSize:14,border:"0.5px solid #D9CDBC",background:"#FFFFFF",color:"#2A2420",outline:"none",boxSizing:"border-box"},
txa:{width:"100%",padding:"11px 12px",borderRadius:10,fontSize:14,minHeight:64,resize:"vertical",border:"0.5px solid #D9CDBC",background:"#FFFFFF",color:"#2A2420",outline:"none",fontFamily:"inherit",boxSizing:"border-box"},
btn:a=>({width:"100%",padding:"13px",borderRadius:12,fontSize:14,fontWeight:600,border:"none",cursor:"pointer",background:a?WINE:"#F5EFE6",color:a?"#FAF7F2":"#2A2420",letterSpacing:0.2}),
bS:{padding:"8px 14px",borderRadius:13,fontSize:12.5,fontWeight:500,border:"0.5px solid #D9CDBC",cursor:"pointer",background:"#FFFFFF",color:"#2A2420"},
bk:{background:"none",border:"none",cursor:"pointer",color:"#6B5F55",fontSize:13,padding:"4px 0",marginBottom:8,display:"flex",alignItems:"center",gap:4},
em:{textAlign:"center",padding:"2.5rem 1rem",color:"#9A8C7E",fontSize:13.5,lineHeight:1.7},
lb:{fontSize:11.5,fontWeight:600,color:"#6B5F55",marginBottom:5,display:"block",letterSpacing:0.3},
mt:{background:"#F5EFE6",borderRadius:12,padding:"12px 8px",textAlign:"center"},
mV:{fontSize:20,fontWeight:600,color:"#2A2420",fontFamily:"'Cormorant Garamond',serif"},
mL:{fontSize:10,color:"#6B5F55",marginTop:2,letterSpacing:0.3},
sc:{fontSize:10.5,fontWeight:600,color:"#9A8C7E",letterSpacing:2,textTransform:"uppercase",margin:"20px 0 8px"},
ai:{background:"#F5EFE6",borderRadius:14,padding:"1rem",marginBottom:10},
bc:{fontSize:12,color:"#9A8C7E",marginBottom:10,display:"flex",flexWrap:"wrap",alignItems:"center",gap:4},
bL:{cursor:"pointer",color:"#6B5F55",background:"none",border:"none",fontSize:12,padding:0,fontFamily:"inherit"},
seg:{display:"flex",background:"#F5EFE6",borderRadius:11,padding:3,marginBottom:14},
segB:a=>({flex:1,padding:"7px 0",borderRadius:8,fontSize:12,fontWeight:600,border:"none",cursor:"pointer",background:a?"#FFFFFF":"transparent",color:a?"#2A2420":"#9A8C7E",boxShadow:a?"0 1px 3px rgba(0,0,0,0.08)":"none",transition:"all 0.15s"}),
chip:a=>({padding:"6px 13px",borderRadius:18,fontSize:12,fontWeight:500,border:"0.5px solid "+(a?"#2A2420":"#D9CDBC"),cursor:"pointer",background:a?"#2A2420":"transparent",color:a?"#FFFFFF":"#6B5F55",whiteSpace:"nowrap"}),
grp:{border:"0.5px solid #E8DFD2",borderRadius:14,overflow:"hidden",marginBottom:14,background:"#FFFFFF"},
row:{display:"flex",alignItems:"center",gap:10,padding:"13px 14px",cursor:"pointer"},
rowDiv:{borderTop:"0.5px solid #E8DFD2"},
chev:{color:"#9A8C7E",fontSize:15,flexShrink:0},
lnk:{background:"none",border:"none",cursor:"pointer",color:GOLD,fontSize:12.5,fontWeight:600,padding:0,fontFamily:"inherit"}};
const ANIM=`@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}@keyframes wvs{from{transform:rotate(0)}to{transform:rotate(360deg)}}`;
const CONTOUR=(cx,cy)=>{const svg="<svg xmlns='http://www.w3.org/2000/svg' width='420' height='320'>"+[70,110,150,190].map(r=>"<circle cx='"+cx+"' cy='"+cy+"' r='"+r+"' fill='none' stroke='"+HAIR+"' stroke-width='1'/>").join("")+"</svg>";return{backgroundImage:'url("data:image/svg+xml,'+encodeURIComponent(svg)+'")',backgroundRepeat:"no-repeat",backgroundPosition:"top right"};};
function PageTitle({children}){return <div style={{fontSize:34,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",lineHeight:1.15,margin:"2px 0 4px"}}>{children}</div>;}

/* ═══════════ SHARED COMPONENTS ═══════════ */
function Stars({value,onChange,size=18}){return <span style={{display:"inline-flex",gap:2}}>{[1,2,3,4,5].map(i=><span key={i} onClick={onChange?()=>onChange(i):undefined} style={{cursor:onChange?"pointer":"default",color:i<=value?GOLD:"#D3D1C7",fontSize:size}}>★</span>)}</span>;}
function Meter({label,v}){return <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:5}}><span style={{fontSize:11,color:"#9A8C7E",width:52}}>{label}</span><span style={{display:"flex",gap:3}}>{[1,2,3,4,5].map(i=><span key={i} style={{width:16,height:5,borderRadius:3,background:i<=v?WINE:"#E8DFD2"}}/>)}</span></div>;}
function VintageChart({regionId}){
  const key=REGION_VINTAGE[regionId];const data=key&&VINTAGES[key];
  const [sel,setSel]=useState(null);
  if(!data)return null;
  const years=Object.keys(data.y).sort();
  return <div style={{...S.cd,cursor:"default"}}>
    <div style={{fontSize:12.5,fontWeight:600,marginBottom:2}}>Vintage chart · {data.name}</div>
    <div style={{fontSize:10.5,color:"#9A8C7E",marginBottom:10}}>2015–2024 · tap a year</div>
    <div style={{display:"flex",alignItems:"flex-end",gap:4,height:56}}>
      {years.map(y=>{const[s]=data.y[y];return <div key={y} onClick={()=>setSel(sel===y?null:y)} style={{flex:1,cursor:"pointer",display:"flex",flexDirection:"column",alignItems:"center",gap:3}}>
        <div style={{width:"100%",maxWidth:22,height:s/5*44,borderRadius:4,background:vScore(s),opacity:sel&&sel!==y?0.35:1,transition:"opacity 0.15s",border:sel===y?"1.5px solid #2A2420":"none",boxSizing:"border-box"}}/>
        <span style={{fontSize:8.5,color:"#9A8C7E"}}>{String(y).slice(2)}</span>
      </div>;})}
    </div>
    {sel&&<div style={{marginTop:10,padding:"8px 10px",background:"#F5EFE6",borderRadius:10,fontSize:12.5}}>
      <span style={{fontWeight:600}}>{sel}</span> <span style={{color:vScore(data.y[sel][0]),fontWeight:600}}>{data.y[sel][0]}/5</span>
      <span style={{color:"#6B5F55"}}> — {data.y[sel][1]}</span>
    </div>}
  </div>;
}
function CollapsibleVintage({regionId}){
  const [open,setOpen]=useState(false);
  const key=REGION_VINTAGE[regionId];
  if(!key)return null;
  if(open)return <VintageChart regionId={regionId}/>;
  return <div style={{...S.grp,...S.row,justifyContent:"space-between",marginBottom:10}} onClick={()=>setOpen(true)}>
    <span style={{fontSize:13,fontWeight:600}}>Vintage chart · {VINTAGES[key].name}</span><span style={S.chev}>›</span>
  </div>;
}
function VarietalCard({grape,color}){
  const [open,setOpen]=useState(false);
  const key=normGrape(grape);const p=key&&VARIETALS[key];
  if(!p)return <span style={S.bg(color)}>{grape}</span>;
  return <div style={{...S.cd,cursor:"pointer",padding:"0.85rem 1rem"}} onClick={()=>setOpen(!open)}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}>
        <span style={{width:10,height:10,borderRadius:5,background:p.t==="r"?WINE:GOLD,display:"inline-block"}}/>
        <span style={{fontWeight:600,fontSize:14,fontFamily:"'Cormorant Garamond',serif"}}>{key}</span>
        {key.toLowerCase()!==grape.toLowerCase()&&<span style={{fontSize:10.5,color:"#9A8C7E"}}>({grape})</span>}
      </div>
      <span style={{fontSize:13,color:"#9A8C7E",transform:open?"rotate(90deg)":"none",transition:"transform 0.15s"}}>›</span>
    </div>
    {open&&<div style={{marginTop:10,animation:"fadeUp 0.2s ease"}}>
      <div style={{fontSize:12.5,color:"#6B5F55",lineHeight:1.6,marginBottom:10}}>{p.notes}</div>
      <Meter label="Body" v={p.body}/><Meter label="Tannin" v={p.tan}/><Meter label="Acidity" v={p.acid}/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,margin:"10px 0"}}>
        <div style={{...S.mt,padding:"8px"}}><div style={{fontSize:12,fontWeight:600}}>{p.age}</div><div style={S.mL}>aging potential</div></div>
        <div style={{...S.mt,padding:"8px"}}><div style={{fontSize:12,fontWeight:600}}>{p.temp}</div><div style={S.mL}>serve at</div></div>
      </div>
      <div style={{fontSize:10.5,fontWeight:600,color:"#9A8C7E",letterSpacing:1.5,textTransform:"uppercase",marginBottom:5}}>Pair with</div>
      {p.pair.map((x,i)=><div key={i} style={{fontSize:12.5,color:"#6B5F55",marginBottom:3}}>· {x}</div>)}
    </div>}
  </div>;
}
function AISec({title,prompt,cacheKey,cache}){
  const [data,setData]=useState(cache.current[cacheKey]||null);
  const [loading,setLoading]=useState(false);
  const [open,setOpen]=useState(false);
  const [err,setErr]=useState(null);
  const load=async()=>{setOpen(true);setErr(null);if(cache.current[cacheKey]){setData(cache.current[cacheKey]);return;}setLoading(true);const r=await askAI(prompt,cacheKey);if(r&&!r._error){cache.current[cacheKey]=r;setData(r);}else setErr(r?._error||"Couldn't load");setLoading(false);};
  if(!open)return <button style={{...S.bS,width:"100%",marginBottom:8,display:"flex",alignItems:"center",justifyContent:"space-between"}} onClick={load}><span>{title}</span><span style={{fontSize:14,opacity:0.4}}>→</span></button>;
  if(loading)return <div style={S.ai}><div style={{fontSize:13,fontWeight:600,marginBottom:8}}>{title}</div><div style={{...S.em,padding:"1rem"}}><div style={{animation:"wvs 1s linear infinite",display:"inline-block",fontSize:20,marginBottom:6}}>🍷</div><div>Consulting the sommelier...</div></div></div>;
  if(!data)return <div style={S.ai}><div style={{fontSize:13,fontWeight:600,marginBottom:6}}>{title}</div><div style={{fontSize:12,color:"#9A8C7E",marginBottom:8}}>{err}</div><button style={{...S.bS,fontSize:12}} onClick={load}>Retry</button></div>;
  return <div style={S.ai}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}><div style={{fontSize:13,fontWeight:600}}>{title}</div><button style={{...S.bL,fontSize:16}} onClick={()=>setOpen(false)}>×</button></div>
    {data.summary&&<p style={{fontSize:13,lineHeight:1.7,color:"#6B5F55",margin:"0 0 10px"}}>{data.summary}</p>}
    {data.pitch&&<p style={{fontSize:13,lineHeight:1.7,color:"#6B5F55",margin:"0 0 10px"}}>{data.pitch}</p>}
    {data.pairings?.length>0&&<div style={{marginBottom:8}}>{data.pairings.map((p,i)=><div key={i} style={{marginBottom:6}}><div style={{fontSize:13,fontWeight:600}}>{p.dish}</div><div style={{fontSize:12,color:"#9A8C7E",lineHeight:1.5}}>{p.why}</div></div>)}</div>}
    {data.producers?.length>0&&<div style={{display:"flex",flexWrap:"wrap",gap:4,marginBottom:6}}>{data.producers.map((p,i)=><span key={i} style={S.bg("#888")}>{p}</span>)}</div>}
    {data.wineries?.length>0&&<div>{data.wineries.map((w,i)=><div key={i} style={{padding:"9px 0",borderBottom:i<data.wineries.length-1?"0.5px solid #E8DFD2":"none"}}><div style={{fontSize:13,fontWeight:600}}>{i+1}. {w.name}</div><div style={{fontSize:12,color:"#9A8C7E",marginTop:2,lineHeight:1.5}}>{w.note}</div></div>)}</div>}
    {data.comparison&&<div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:12}}>{data.comparison.map((sd,si)=><div key={si}><div style={{fontSize:13,fontWeight:700,marginBottom:6,fontFamily:"'Cormorant Garamond',serif"}}>{sd.name}</div>{sd.attributes?.map((at,ai2)=><div key={ai2} style={{marginBottom:6}}><div style={{fontSize:10.5,fontWeight:600,color:"#9A8C7E",textTransform:"uppercase",letterSpacing:0.5}}>{at.label}</div><div style={{fontSize:12,color:"#6B5F55",lineHeight:1.5}}>{at.value}</div></div>)}</div>)}</div>{data.verdict&&<div style={{borderTop:"0.5px solid #E8DFD2",paddingTop:10}}><div style={{fontSize:10.5,fontWeight:600,color:"#9A8C7E",textTransform:"uppercase",letterSpacing:1.5,marginBottom:5}}>Verdict</div><p style={{fontSize:13,lineHeight:1.7,color:"#6B5F55",margin:0}}>{data.verdict}</p></div>}</div>}
  </div>;
}
function Donut({data,total,label}){
  const R=52,IR=34,C=64;let acc=-Math.PI/2;
  const sum=data.reduce((s,d)=>s+d.value,0)||1;
  const arc=(r1,r0,a0,a1)=>{const p=(r,a)=>[C+r*Math.cos(a),C+r*Math.sin(a)];const lg=a1-a0>Math.PI?1:0;const[x0,y0]=p(r1,a0),[x1,y1]=p(r1,a1),[x2,y2]=p(r0,a1),[x3,y3]=p(r0,a0);return`M${x0} ${y0} A${r1} ${r1} 0 ${lg} 1 ${x1} ${y1} L${x2} ${y2} A${r0} ${r0} 0 ${lg} 0 ${x3} ${y3} Z`;};
  return <div style={{display:"flex",alignItems:"center",gap:14}}>
    <svg width={128} height={128} viewBox="0 0 128 128" style={{flexShrink:0}}>
      {data.map((d,i)=>{const a0=acc,a1=acc+(d.value/sum)*Math.PI*2-0.03;acc=a1+0.03;return d.value>0?<path key={i} d={arc(R,IR,a0,Math.max(a1,a0+0.01))} fill={d.color}/>:null;})}
      <text x={C} y={C-4} textAnchor="middle" fontSize="20" fontWeight="600" fill="#2A2420" fontFamily="'Cormorant Garamond',serif">{total}</text>
      <text x={C} y={C+12} textAnchor="middle" fontSize="8.5" fill="#9A8C7E">{label}</text>
    </svg>
    <div style={{flex:1}}>{data.map((d,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}><span style={{width:8,height:8,borderRadius:4,background:d.color,flexShrink:0}}/><span style={{fontSize:11.5,color:"#6B5F55",flex:1}}>{d.label}</span><span style={{fontSize:11.5,fontWeight:600}}>{d.value}</span></div>)}</div>
  </div>;
}
const PALETTE=["#7A2E3B","#BA7517","#4E7C4E","#3E5F8A","#8A5A9E","#A65B4B","#888"];

/* ═══════════ HOME ═══════════ */
function HomeTab({cellar,journal,taste,setTaste,onConsume,goTab}){
  const [pick,setPick]=useState(null);const [picking,setPicking]=useState(false);const ref=useRef(null);
  const drinkNow=cellar.filter(b=>b.qty>0&&bottleStatus(b)==="now");
  const pastPeak=cellar.filter(b=>b.qty>0&&bottleStatus(b)==="past");
  const entering=cellar.filter(b=>b.qty>0&&Number(b.from)===YR);
  const totalBottles=cellar.reduce((s,b)=>s+Number(b.qty||0),0);
  const totalValue=cellar.reduce((s,b)=>s+Number(b.qty||0)*Number(b.value||b.price||0),0);
  const hour=new Date().getHours();
  const greet=hour<12?"Good morning":hour<17?"Good afternoon":"Good evening";
  const [newRef,setNewRef]=useState("");
  const addRef=async()=>{if(!newRef.trim())return;const u=[{id:uid(),name:newRef.trim()},...taste];setTaste(u);await store("wv5-taste",u);setNewRef("");};
  const delRef=async id=>{const u=taste.filter(t=>t.id!==id);setTaste(u);await store("wv5-taste",u);};
  const spinPick=()=>{
    if(drinkNow.length===0)return;
    setPicking(true);setPick(null);let c=0;const total=14+Math.floor(Math.random()*8);
    const tick=()=>{c++;setPick(drinkNow[Math.floor(Math.random()*drinkNow.length)]);if(c<total)ref.current=setTimeout(tick,55+c*14);else setPicking(false);};
    tick();
  };
  useEffect(()=>()=>clearTimeout(ref.current),[]);
  return <div style={{animation:"fadeUp 0.25s ease"}}>
    <div style={{margin:"6px 0 16px"}}>
      <div style={{fontSize:26,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{greet} 🥂</div>
      <div style={{fontSize:12,color:"#9A8C7E",marginTop:2}}>{new Date().toLocaleDateString("en-US",{weekday:"long",month:"long",day:"numeric"})}</div>
    </div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:7,marginBottom:14}}>
      <div style={S.mt}><div style={S.mV}>{totalBottles}</div><div style={S.mL}>bottles</div></div>
      <div style={S.mt}><div style={{...S.mV,fontSize:15,paddingTop:4}}>{fmt$(totalValue)}</div><div style={S.mL}>value</div></div>
      <div style={S.mt}><div style={S.mV}>{drinkNow.length}</div><div style={S.mL}>drink now</div></div>
      <div style={S.mt}><div style={S.mV}>{journal.length}</div><div style={S.mL}>tastings</div></div>
    </div>
    <div style={{...S.cd,background:"linear-gradient(135deg,"+WINE+"14,"+GOLD+"10)",cursor:"default"}}>
      <div style={{fontSize:14,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginBottom:4}}>What should we open tonight?</div>
      {drinkNow.length===0?<div style={{fontSize:12.5,color:"#9A8C7E"}}>Add bottles with drink windows to your cellar and I'll pick.</div>:<>
        {pick&&<div style={{margin:"8px 0",padding:"10px 12px",background:"#FFFFFF",borderRadius:10,animation:picking?"none":"fadeUp 0.25s ease"}}>
          <div style={{fontWeight:600,fontSize:14,fontFamily:"'Cormorant Garamond',serif"}}>{pick.producer} {pick.wine}</div>
          <div style={{fontSize:11.5,color:"#9A8C7E"}}>{[pick.vintage,pick.varietal,pick.appellation].filter(Boolean).join(" · ")}{pick.loc?` · ${pick.loc}`:""}</div>
          {!picking&&<button style={{...S.bS,marginTop:8,fontSize:12}} onClick={()=>onConsume(pick)}>Open this bottle 🍾</button>}
        </div>}
        <button style={{...S.btn(true),marginTop:pick?0:8}} onClick={spinPick} disabled={picking}>{picking?"Choosing...":pick?"Pick again":"Pick a bottle"}</button>
      </>}
    </div>
    {(pastPeak.length>0||entering.length>0)&&<><div style={S.sc}>Cellar alerts</div>
      {entering.slice(0,3).map(b=><div key={b.id} style={{...S.cd,cursor:"default",padding:"0.8rem 1rem"}}><span style={S.pill("#4E7C4E")}>Entering window</span><div style={{fontSize:13.5,fontWeight:600,marginTop:5}}>{b.producer} {b.wine} {b.vintage}</div><div style={{fontSize:11.5,color:"#9A8C7E"}}>Drink window opens this year</div></div>)}
      {pastPeak.slice(0,3).map(b=><div key={b.id} style={{...S.cd,cursor:"default",padding:"0.8rem 1rem"}}><span style={S.pill("#A65B4B")}>Past peak</span><div style={{fontSize:13.5,fontWeight:600,marginTop:5}}>{b.producer} {b.wine} {b.vintage}</div><div style={{fontSize:11.5,color:"#9A8C7E"}}>Window closed {b.to} — open soon</div></div>)}
    </>}
    <div style={S.sc}>Your benchmark producers</div>
    <div style={{...S.cd,cursor:"default"}}>
      <div style={{display:"flex",flexWrap:"wrap",gap:5,marginBottom:taste.length?10:0}}>
        {taste.map(t=><span key={t.id} style={{...S.bg(GOLD),display:"inline-flex",alignItems:"center",gap:5}}>{t.name}<span style={{cursor:"pointer",opacity:0.6}} onClick={()=>delRef(t.id)}>×</span></span>)}
        {taste.length===0&&<span style={{fontSize:12,color:"#9A8C7E"}}>Add winemakers you trust — they'll power the recommendation engine on your Mac mini backend.</span>}
      </div>
      <div style={{display:"flex",gap:8}}>
        <input style={{...S.inp,flex:1}} placeholder="e.g. Arista" value={newRef} onChange={e=>setNewRef(e.target.value)}/>
        <button style={{...S.bS,flexShrink:0}} onClick={addRef}>Add</button>
      </div>
    </div>
    {journal.length>0&&<><div style={S.sc}>Last tasting</div>
      <div style={{...S.cdT}} onClick={()=>goTab("journal")}>
        <div style={{fontWeight:600,fontSize:14,fontFamily:"'Cormorant Garamond',serif"}}>{journal[0].name}</div>
        <div style={{fontSize:11.5,color:"#9A8C7E",marginTop:2}}>{journal[0].date}</div>
        <div style={{display:"flex",gap:14,marginTop:6}}><span style={{fontSize:11.5,color:"#6B5F55"}}>Him <Stars value={journal[0].hisRating} size={12}/></span><span style={{fontSize:11.5,color:"#6B5F55"}}>Her <Stars value={journal[0].herRating} size={12}/></span></div>
      </div></>}
  </div>;
}

/* ═══════════ ATLAS ═══════════ */
function AtlasTab({cache,trips,onAddTrip}){
  const [mode,setMode]=useState("explore");
  const [path,setPath]=useState([]);
  const [rootQ,setRootQ]=useState("");
  const [a1,setA1]=useState(null);const [a2,setA2]=useState(null);const [s1,setS1]=useState("");const [s2,setS2]=useState("");
  const saved=id=>trips.some(t=>t.appellationId===id);
  const filter=q=>q.length<2?[]:allApps.filter(a=>(a.name+" "+a.regionName+" "+a.countryName).toLowerCase().includes(q.toLowerCase())).slice(0,8);
  const jump=a=>{setPath([{id:a.countryId,label:a.countryName},{id:a.regionId,label:a.regionName},{id:a.id,label:a.name}]);setRootQ("");};
  const Picker=({value,onChange,search,setSearch,label,other})=>{
    if(value)return <div style={{...S.ai,marginBottom:0,display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><span style={{marginRight:5}}>{value.countryEmoji}</span><span style={{fontWeight:600,fontSize:14,fontFamily:"'Cormorant Garamond',serif"}}>{value.name}</span><div style={{fontSize:11,color:"#9A8C7E"}}>{value.regionName}, {value.countryName}</div></div><button style={{...S.bL,fontSize:15}} onClick={()=>{onChange(null);setSearch("");}}>×</button></div>;
    const res=filter(search).filter(a=>a.id!==other?.id);
    return <div><label style={S.lb}>{label}</label><input style={S.inp} placeholder="Search appellations..." value={search} onChange={e=>setSearch(e.target.value)}/>{res.length>0&&<div style={{...S.grp,marginTop:6}}>{res.map((a,i)=><div key={a.id} style={{...S.row,...(i?S.rowDiv:{})}} onClick={()=>{onChange(a);setSearch("");}}><span>{a.countryEmoji}</span><span style={{fontSize:13,flex:1}}>{a.name}<span style={{color:"#9A8C7E",marginLeft:6,fontSize:11}}>{a.regionName}</span></span></div>)}</div>}</div>;
  };
  if(mode==="compare")return <div style={{animation:"fadeUp 0.25s ease"}}>
    <button style={S.bk} onClick={()=>setMode("explore")}>← Atlas</button>
    <div style={{fontSize:30,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginBottom:12}}>Compare</div>
    <div style={{display:"flex",flexDirection:"column",gap:12,marginBottom:14}}>
      <Picker value={a1} onChange={setA1} search={s1} setSearch={setS1} label="First appellation" other={a2}/>
      <div style={{textAlign:"center",fontSize:11,color:"#9A8C7E"}}>vs</div>
      <Picker value={a2} onChange={setA2} search={s2} setSearch={setS2} label="Second appellation" other={a1}/>
    </div>
    {a1&&a2&&<AISec cache={cache} title={`${a1.name} vs ${a2.name}`} cacheKey={`cmp-${[a1.id,a2.id].sort().join("-")}`}
      prompt={`Compare ${a1.name} (${a1.regionName}, ${a1.countryName} — ${a1.grapes.join(", ")}) vs ${a2.name} (${a2.regionName}, ${a2.countryName} — ${a2.grapes.join(", ")}). JSON: {"comparison":[{"name":"${a1.name}","attributes":[{"label":"Climate","value":"..."},{"label":"Key Grape","value":"..."},{"label":"Price Range","value":"$ to $$$$"},{"label":"Best For","value":"..."},{"label":"Visit Season","value":"..."}]},{"name":"${a2.name}","attributes":[{"label":"Climate","value":"..."},{"label":"Key Grape","value":"..."},{"label":"Price Range","value":"$ to $$$$"},{"label":"Best For","value":"..."},{"label":"Visit Season","value":"..."}]}],"verdict":"3 sentences: who should choose which and why. Be opinionated."}`}/>}
  </div>;
  if(path.length===0){
    const res=filter(rootQ);
    return <div style={{animation:"fadeUp 0.25s ease",...CONTOUR(340,10)}}>
      <PageTitle>Atlas</PageTitle>
      <input style={{...S.inp,marginBottom:12}} placeholder="Jump to an appellation..." value={rootQ} onChange={e=>setRootQ(e.target.value)}/>
      {rootQ.length>=2?(res.length?<div style={S.grp}>{res.map((a,i)=><div key={a.id} style={{...S.row,...(i?S.rowDiv:{})}} onClick={()=>jump(a)}>
        <span style={{fontSize:17}}>{a.countryEmoji}</span>
        <span style={{flex:1,minWidth:0}}><span style={{display:"block",fontSize:14,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{a.name}</span><span style={{fontSize:11,color:"#9A8C7E"}}>{a.regionName} · {a.countryName}</span></span>
        <span style={S.chev}>›</span>
      </div>)}</div>:<div style={S.em}>No matches.</div>)
      :<>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",margin:"2px 0 8px"}}>
        <span style={{...S.sc,margin:0}}>Countries</span>
        <button style={S.lnk} onClick={()=>setMode("compare")}>Compare two →</button>
      </div>
      <div style={S.grp}>{W.countries.map((c,i)=><div key={c.id} style={{...S.row,...(i?S.rowDiv:{})}} onClick={()=>setPath([{id:c.id,label:c.name}])}>
        <span style={{fontSize:19}}>{c.emoji}</span>
        <span style={{flex:1,fontSize:15,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{c.name}</span>
        <span style={S.chev}>›</span>
      </div>)}</div>
      </>}
    </div>;
  }
  const country=W.countries.find(c=>c.id===path[0]?.id);if(!country)return null;
  if(path.length===1)return <div style={{animation:"fadeUp 0.25s ease",...CONTOUR(350,40)}}>
    <button style={S.bk} onClick={()=>setPath([])}>← Atlas</button>
    <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:12}}><span style={{fontSize:28}}>{country.emoji}</span><span style={{fontSize:32,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{country.name}</span></div>
    <div style={S.grp}>{country.regions.map((r,i)=>{const gs=[...new Set(r.appellations.flatMap(a=>a.grapes))].slice(0,3).join(" · ");
      return <div key={r.id} style={{...S.row,...(i?S.rowDiv:{})}} onClick={()=>setPath([...path,{id:r.id,label:r.name}])}>
        <span style={{flex:1,minWidth:0}}><span style={{display:"block",fontSize:15,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{r.name}</span><span style={{fontSize:11.5,color:"#9A8C7E"}}>{gs}</span></span>
        <span style={S.chev}>›</span>
      </div>;})}</div>
  </div>;
  const region=country.regions.find(r=>r.id===path[1]?.id);if(!region)return null;
  if(path.length===2)return <div style={{animation:"fadeUp 0.25s ease",...CONTOUR(30,120)}}>
    <button style={S.bk} onClick={()=>setPath(path.slice(0,1))}>← {country.name}</button>
    <div style={{fontSize:10,fontWeight:600,letterSpacing:2,color:"#9A8C7E",textTransform:"uppercase"}}>{country.name} · {region.appellations.length} appellations</div>
    <div style={{fontSize:34,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",lineHeight:1.15,margin:"3px 0 12px"}}>{region.name}</div>
    <VintageChart regionId={region.id}/>
    <div style={S.grp}>{region.appellations.map((a,i)=><div key={a.id} style={{...S.row,...(i?S.rowDiv:{})}} onClick={()=>setPath([...path,{id:a.id,label:a.name}])}>
      <span style={{flex:1,minWidth:0}}><span style={{display:"block",fontSize:15,fontWeight:600,fontFamily:"'Cormorant Garamond',serif"}}>{a.name}{saved(a.id)&&<span style={{fontSize:11,color:"#4E7C4E",marginLeft:6}}>✓</span>}</span><span style={{fontSize:12,color:"#6B5F55",lineHeight:1.45}}>{a.style}</span></span>
      <span style={S.chev}>›</span>
    </div>)}</div>
  </div>;
  const app=region.appellations.find(a=>a.id===path[2]?.id);if(!app)return null;
  const gl=app.grapes.join(", ");
  return <div style={{animation:"fadeUp 0.25s ease",...CONTOUR(360,70)}}>
    <button style={S.bk} onClick={()=>setPath(path.slice(0,2))}>← {region.name}</button>
    <div style={{fontSize:10,fontWeight:600,letterSpacing:2,color:"#9A8C7E",textTransform:"uppercase"}}>{region.name} · {country.name}</div>
    <div style={{fontSize:32,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",lineHeight:1.15,margin:"3px 0 6px"}}>{app.name}</div>
    <p style={{fontFamily:"'Cormorant Garamond',serif",fontStyle:"italic",fontSize:16,lineHeight:1.5,color:"#6B5F55",margin:"0 0 12px"}}>{app.style}</p>
    <div style={S.sc}>The grapes</div>
    {app.grapes.map(g=><VarietalCard key={g} grape={g} color={country.color}/>)}
    <div style={{marginTop:14}}/>
    <CollapsibleVintage key={app.id} regionId={region.id}/>
    <div style={S.sc}>Sommelier deep dives</div>
    <AISec cache={cache} title={`Insider guide to ${app.name}`} cacheKey={`abt-${app.id}`} prompt={`About ${app.name} in ${region.name}, ${country.name}. JSON: {"summary":"3 sentences — terroir, history, what makes it special","producers":["5-6 famous producer names"]}`}/>
    <AISec cache={cache} title="Notable wineries" cacheKey={`win-${app.id}`} prompt={`For a wine guidebook entry on ${app.name} (${region.name}, ${country.name}), list 15 notable wineries. Return this exact JSON: {"wineries":[{"name":"Winery Name","note":"flagship wine and signature style in 10 words"}]} Sort by historical importance. Include both established names and exciting newer producers.`}/>
    <AISec cache={cache} title="Food pairings" cacheKey={`food-${app.id}`} prompt={`Food pairings for ${app.name} wines (${gl}). JSON: {"pairings":[{"dish":"specific dish","why":"1 sentence"}]} 5-6 pairings: local + global.`}/>
    <div style={{marginTop:14}}>{saved(app.id)?<div style={{textAlign:"center",fontSize:13,color:"#4E7C4E",padding:10}}>✓ On your voyage list</div>:<button style={S.btn(true)} onClick={()=>onAddTrip({...app,regionName:region.name,countryName:country.name,countryEmoji:country.emoji,countryColor:country.color})}>Add to voyage list</button>}</div>
  </div>;
}

/* ═══════════ CELLAR ═══════════ */
function CellarTab({cellar,setCellar,onConsume}){
  const [view,setView]=useState("list");
  const [adding,setAdding]=useState(false);
  const [importing,setImporting]=useState(false);
  const [exporting,setExporting]=useState(false);
  const [csv,setCsv]=useState("");
  const [q,setQ]=useState("");
  const [filt,setFilt]=useState("all");
  const blank={producer:"",wine:"",vintage:"",varietal:"",appellation:"",qty:1,size:"750ml",price:"",value:"",loc:"",from:"",to:"",notes:""};
  const [form,setForm]=useState(blank);
  const save=async()=>{if(!form.producer&&!form.wine)return;const b={...form,id:uid(),qty:Number(form.qty)||1,addedAt:Date.now()};const u=[b,...cellar];setCellar(u);await store("wv5-cellar",u);setForm(blank);setAdding(false);};
  const del=async id=>{const u=cellar.filter(b=>b.id!==id);setCellar(u);await store("wv5-cellar",u);};
  const adjQty=async(id,d)=>{const u=cellar.map(b=>b.id===id?{...b,qty:Math.max(0,Number(b.qty)+d)}:b);setCellar(u);await store("wv5-cellar",u);};
  const runImport=async()=>{
    const lines=csv.trim().split(/\r?\n/).filter(l=>l.trim());if(lines.length===0)return;
    const delim=lines[0].includes("\t")?"\t":lines[0].includes(";")?";":",";
    let start=0;const hdr=lines[0].toLowerCase().split(delim).map(h=>h.trim());
    const looks=hdr.some(h=>/producer|winery|wine|name|vintage|year/.test(h));
    const col=n=>hdr.findIndex(h=>n.some(x=>h.includes(x)));
    let map={producer:0,wine:1,vintage:2,varietal:3,qty:4,price:5,loc:6};
    if(looks){start=1;map={producer:col(["producer","winery","estate"]),wine:col(["wine","name","label","cuvee"]),vintage:col(["vintage","year"]),varietal:col(["varietal","grape","variety"]),qty:col(["qty","quantity","bottles","count"]),price:col(["price","cost","value","paid"]),loc:col(["loc","bin","rack","position"])};}
    const items=lines.slice(start).map(l=>{const c=l.split(delim).map(x=>x.trim().replace(/^"|"$/g,""));const g=i=>i>=0&&c[i]?c[i]:"";
      return{id:uid(),producer:g(map.producer),wine:g(map.wine),vintage:g(map.vintage),varietal:g(map.varietal),appellation:"",qty:Number(g(map.qty))||1,size:"750ml",price:g(map.price).replace(/[^0-9.]/g,""),value:"",loc:g(map.loc),from:"",to:"",notes:"",addedAt:Date.now()};}).filter(b=>b.producer||b.wine);
    const u=[...items,...cellar];setCellar(u);await store("wv5-cellar",u);setCsv("");setImporting(false);
  };
  const exportCsv=()=>{const h="producer,wine,vintage,varietal,appellation,qty,size,price,value,location,drink_from,drink_to,notes";
    const rows=cellar.map(b=>[b.producer,b.wine,b.vintage,b.varietal,b.appellation,b.qty,b.size,b.price,b.value,b.loc,b.from,b.to,(b.notes||"").replace(/,/g,";")].join(","));
    return[h,...rows].join("\n");};
  const totalBottles=cellar.reduce((s,b)=>s+Number(b.qty||0),0);
  const totalValue=cellar.reduce((s,b)=>s+Number(b.qty||0)*Number(b.value||b.price||0),0);
  const uniq=cellar.length;
  const ready=cellar.filter(b=>b.qty>0&&bottleStatus(b)==="now").length;
  const byVar={};cellar.forEach(b=>{if(b.qty>0){const k=b.varietal||"Other";byVar[k]=(byVar[k]||0)+Number(b.qty);}});
  const varData=Object.entries(byVar).sort((a,b)=>b[1]-a[1]);
  const donut=[...varData.slice(0,6).map(([l,v],i)=>({label:l,value:v,color:PALETTE[i]})),...(varData.length>6?[{label:"Other",value:varData.slice(6).reduce((s,[,v])=>s+v,0),color:PALETTE[6]}]:[])];
  const byYear={};cellar.forEach(b=>{if(b.qty>0&&b.vintage){byYear[b.vintage]=(byYear[b.vintage]||0)+Number(b.qty);}});
  const years=Object.keys(byYear).sort();
  const maxY=Math.max(...Object.values(byYear),1);
  const list=cellar.filter(b=>{
    if(filt!=="all"&&bottleStatus(b)!==filt)return false;
    if(q&&!(b.producer+" "+b.wine+" "+b.varietal+" "+b.appellation).toLowerCase().includes(q.toLowerCase()))return false;
    return true;});
  if(adding)return <div style={{animation:"fadeUp 0.25s ease"}}>
    <button style={S.bk} onClick={()=>setAdding(false)}>← Cellar</button>
    <div style={{fontSize:18,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginBottom:12}}>Add a bottle</div>
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <div><label style={S.lb}>Producer</label><input style={S.inp} placeholder="Arista" value={form.producer} onChange={e=>setForm({...form,producer:e.target.value})}/></div>
        <div><label style={S.lb}>Wine</label><input style={S.inp} placeholder="Toboni Pinot Noir" value={form.wine} onChange={e=>setForm({...form,wine:e.target.value})}/></div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
        <div><label style={S.lb}>Vintage</label><input style={S.inp} inputMode="numeric" placeholder="2021" value={form.vintage} onChange={e=>setForm({...form,vintage:e.target.value})}/></div>
        <div><label style={S.lb}>Qty</label><input style={S.inp} inputMode="numeric" value={form.qty} onChange={e=>setForm({...form,qty:e.target.value})}/></div>
        <div><label style={S.lb}>Size</label><select style={S.inp} value={form.size} onChange={e=>setForm({...form,size:e.target.value})}>{["375ml","750ml","1.5L","3L"].map(s=><option key={s}>{s}</option>)}</select></div>
      </div>
      <div><label style={S.lb}>Varietal</label><input list="wv-varietals" style={S.inp} placeholder="Pinot Noir" value={form.varietal} onChange={e=>setForm({...form,varietal:e.target.value})}/><datalist id="wv-varietals">{Object.keys(VARIETALS).map(v=><option key={v} value={v}/>)}</datalist></div>
      <div><label style={S.lb}>Appellation</label><input list="wv-apps" style={S.inp} placeholder="Russian River Valley" value={form.appellation} onChange={e=>setForm({...form,appellation:e.target.value})}/><datalist id="wv-apps">{allApps.map(a=><option key={a.id} value={a.name}/>)}</datalist></div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <div><label style={S.lb}>Purchase price ($)</label><input style={S.inp} inputMode="decimal" placeholder="65" value={form.price} onChange={e=>setForm({...form,price:e.target.value})}/></div>
        <div><label style={S.lb}>Est. value ($)</label><input style={S.inp} inputMode="decimal" placeholder="85" value={form.value} onChange={e=>setForm({...form,value:e.target.value})}/></div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
        <div><label style={S.lb}>Location</label><input style={S.inp} placeholder="Rack A · Bin 3" value={form.loc} onChange={e=>setForm({...form,loc:e.target.value})}/></div>
        <div><label style={S.lb}>Drink from</label><input style={S.inp} inputMode="numeric" placeholder="2026" value={form.from} onChange={e=>setForm({...form,from:e.target.value})}/></div>
        <div><label style={S.lb}>Drink to</label><input style={S.inp} inputMode="numeric" placeholder="2034" value={form.to} onChange={e=>setForm({...form,to:e.target.value})}/></div>
      </div>
      <div><label style={S.lb}>Notes</label><textarea style={S.txa} placeholder="Gift from the tasting room visit..." value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></div>
      <button style={S.btn(true)} onClick={save}>Add to cellar</button>
    </div>
  </div>;
  if(importing)return <div style={{animation:"fadeUp 0.25s ease"}}>
    <button style={S.bk} onClick={()=>setImporting(false)}>← Cellar</button>
    <div style={{fontSize:18,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginBottom:6}}>Import from CSV</div>
    <div style={{fontSize:12.5,color:"#9A8C7E",lineHeight:1.6,marginBottom:10}}>Paste a CSV export (OENO, CellarTracker, or a spreadsheet). Header row with producer / wine / vintage / varietal / qty / price columns is auto-detected; otherwise columns are read in that order.</div>
    <textarea style={{...S.txa,minHeight:150,fontFamily:"monospace",fontSize:12}} placeholder={"producer,wine,vintage,varietal,qty,price\nArista,Toboni Pinot Noir,2021,Pinot Noir,3,75"} value={csv} onChange={e=>setCsv(e.target.value)}/>
    <button style={{...S.btn(true),marginTop:10}} onClick={runImport}>Import {csv.trim()?`${csv.trim().split(/\r?\n/).length} line(s)`:""}</button>
  </div>;
  if(exporting)return <div style={{animation:"fadeUp 0.25s ease"}}>
    <button style={S.bk} onClick={()=>setExporting(false)}>← Cellar</button>
    <div style={{fontSize:18,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginBottom:6}}>Export CSV</div>
    <div style={{fontSize:12.5,color:"#9A8C7E",marginBottom:10}}>Select all and copy — paste into any spreadsheet or your backend seed.</div>
    <textarea readOnly style={{...S.txa,minHeight:200,fontFamily:"monospace",fontSize:11.5}} value={exportCsv()} onFocus={e=>e.target.select()}/>
  </div>;
  return <div style={{animation:"fadeUp 0.25s ease"}}>
    <PageTitle>Cellar</PageTitle>
    {cellar.length>0&&<div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:7,marginBottom:12}}>
      <div style={S.mt}><div style={S.mV}>{totalBottles}</div><div style={S.mL}>bottles</div></div>
      <div style={S.mt}><div style={S.mV}>{uniq}</div><div style={S.mL}>wines</div></div>
      <div style={S.mt}><div style={{...S.mV,fontSize:15,paddingTop:4}}>{fmt$(totalValue)}</div><div style={S.mL}>value</div></div>
      <div style={S.mt}><div style={S.mV}>{ready}</div><div style={S.mL}>ready</div></div>
    </div>}
    <div style={{display:"flex",gap:8,marginBottom:12}}>
      <button style={{...S.btn(true),flex:1}} onClick={()=>setAdding(true)}>+ Add bottle</button>
      <button style={{...S.bS,flexShrink:0}} onClick={()=>setImporting(true)}>Import</button>
      {cellar.length>0&&<button style={{...S.bS,flexShrink:0}} onClick={()=>setExporting(true)}>Export</button>}
    </div>
    {cellar.length===0?<div style={S.em}><div style={{fontSize:32,marginBottom:8}}>🍾</div>Your cellar starts here.<br/>Add bottles by hand or import a CSV from OENO.</div>:<>
    <div style={S.seg}><button style={S.segB(view==="list")} onClick={()=>setView("list")}>Inventory</button><button style={S.segB(view==="stats")} onClick={()=>setView("stats")}>Insights</button></div>
    {view==="stats"?<div>
      <div style={{...S.cd,cursor:"default"}}><div style={{fontSize:12.5,fontWeight:600,marginBottom:10}}>Composition by varietal</div><Donut data={donut} total={totalBottles} label="bottles"/></div>
      {years.length>0&&<div style={{...S.cd,cursor:"default"}}><div style={{fontSize:12.5,fontWeight:600,marginBottom:10}}>Bottles by vintage</div>
        <div style={{display:"flex",alignItems:"flex-end",gap:4,height:64}}>{years.map(y=><div key={y} style={{flex:1,display:"flex",flexDirection:"column",alignItems:"center",gap:3}}><span style={{fontSize:9,color:"#6B5F55"}}>{byYear[y]}</span><div style={{width:"100%",maxWidth:24,height:Math.max(6,byYear[y]/maxY*44),borderRadius:4,background:WINE}}/><span style={{fontSize:8.5,color:"#9A8C7E"}}>{String(y).slice(2)}</span></div>)}</div>
      </div>}
      <div style={{...S.cd,cursor:"default"}}><div style={{fontSize:12.5,fontWeight:600,marginBottom:8}}>Drink window status</div>
        {["now","hold","past"].map(st=>{const n=cellar.filter(b=>b.qty>0&&bottleStatus(b)===st).reduce((s,b)=>s+Number(b.qty),0);return <div key={st} style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}><span style={S.pill(STATUS[st].c)}>{STATUS[st].l}</span><div style={{flex:1,height:7,background:"#F5EFE6",borderRadius:4,overflow:"hidden"}}><div style={{width:`${totalBottles?n/totalBottles*100:0}%`,height:"100%",background:STATUS[st].c,borderRadius:4}}/></div><span style={{fontSize:12,fontWeight:600,width:26,textAlign:"right"}}>{n}</span></div>;})}
      </div>
    </div>:<>
    <input style={{...S.inp,marginBottom:10}} placeholder="Search cellar..." value={q} onChange={e=>setQ(e.target.value)}/>
    <div style={{display:"flex",gap:6,overflowX:"auto",paddingBottom:4,marginBottom:10}}>
      {[["all","All"],["now","Drink now"],["hold","Hold"],["past","Past peak"]].map(([k,l])=><button key={k} style={S.chip(filt===k)} onClick={()=>setFilt(k)}>{l}</button>)}
    </div>
    {list.length===0&&<div style={S.em}>No bottles match.</div>}
    {list.map(b=>{const st=bottleStatus(b);return <div key={b.id} style={{...S.cd,cursor:"default",opacity:b.qty===0?0.5:1}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontWeight:600,fontSize:14.5,fontFamily:"'Cormorant Garamond',serif"}}>{b.producer} {b.wine}</div>
          <div style={{fontSize:11.5,color:"#9A8C7E",marginTop:2}}>{[b.vintage,b.varietal,b.appellation,b.size!=="750ml"?b.size:null].filter(Boolean).join(" · ")}</div>
          {b.loc&&<div style={{fontSize:11,color:"#9A8C7E",marginTop:2}}>📍 {b.loc}</div>}
        </div>
        <button onClick={()=>del(b.id)} style={{background:"none",border:"none",cursor:"pointer",color:"#9A8C7E",fontSize:15,padding:"0 2px"}}>×</button>
      </div>
      <div style={{display:"flex",alignItems:"center",gap:8,marginTop:9,flexWrap:"wrap"}}>
        <span style={S.pill(STATUS[st].c)}>{STATUS[st].l}{b.from||b.to?` ${b.from||""}–${b.to||""}`:""}</span>
        {(b.value||b.price)&&<span style={{fontSize:11.5,color:"#6B5F55",fontWeight:600}}>{fmt$(b.value||b.price)}/btl</span>}
        <span style={{flex:1}}/>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <button style={{...S.bS,padding:"4px 11px"}} onClick={()=>adjQty(b.id,-1)}>−</button>
          <span style={{fontSize:14,fontWeight:600,minWidth:18,textAlign:"center"}}>{b.qty}</span>
          <button style={{...S.bS,padding:"4px 11px"}} onClick={()=>adjQty(b.id,1)}>+</button>
        </div>
      </div>
      {b.qty>0&&<button style={{...S.bS,width:"100%",marginTop:9,fontSize:12}} onClick={()=>onConsume(b)}>Open a bottle 🍾 → log tasting</button>}
    </div>;})}</>}</>}
  </div>;
}

/* ═══════════ JOURNAL ═══════════ */
function JournalTab({journal,setJournal,draft,clearDraft}){
  const [adding,setAdding]=useState(false);
  const blank={name:"",region:"",vintage:"",hisRating:0,herRating:0,notes:""};
  const [form,setForm]=useState(blank);
  useEffect(()=>{if(draft){setForm({...blank,...draft});setAdding(true);clearDraft();}},[draft]);
  const save=async()=>{if(!form.name)return;const e={...form,id:uid(),date:new Date().toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})};const u=[e,...journal];setJournal(u);await store("wv5-journal",u);setForm(blank);setAdding(false);};
  const del=async id=>{const u=journal.filter(e=>e.id!==id);setJournal(u);await store("wv5-journal",u);};
  const aH=journal.length?(journal.reduce((s,e)=>s+e.hisRating,0)/journal.length).toFixed(1):"—";
  const aS=journal.length?(journal.reduce((s,e)=>s+e.herRating,0)/journal.length).toFixed(1):"—";
  const ag=journal.length?Math.round(journal.filter(e=>Math.abs(e.hisRating-e.herRating)<=1).length/journal.length*100):0;
  if(adding)return <div style={{animation:"fadeUp 0.25s ease"}}>
    <button style={S.bk} onClick={()=>{setAdding(false);setForm(blank);}}>← Journal</button>
    <div style={{display:"flex",flexDirection:"column",gap:12}}>
      <div><label style={S.lb}>Wine</label><input style={S.inp} placeholder="e.g. Barolo Riserva 2018" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <div><label style={S.lb}>Region</label><input style={S.inp} placeholder="Piedmont" value={form.region} onChange={e=>setForm({...form,region:e.target.value})}/></div>
        <div><label style={S.lb}>Vintage</label><input style={S.inp} placeholder="2018" value={form.vintage} onChange={e=>setForm({...form,vintage:e.target.value})}/></div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
        <div><label style={S.lb}>His rating</label><Stars value={form.hisRating} onChange={v=>setForm({...form,hisRating:v})}/></div>
        <div><label style={S.lb}>Her rating</label><Stars value={form.herRating} onChange={v=>setForm({...form,herRating:v})}/></div>
      </div>
      <div><label style={S.lb}>Tasting notes</label><textarea style={S.txa} placeholder="What did you both think?" value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></div>
      <button style={S.btn(true)} onClick={save}>Save tasting</button>
    </div>
  </div>;
  return <div style={{animation:"fadeUp 0.25s ease"}}>
    <PageTitle>Journal</PageTitle>
    {journal.length>0&&<div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:7,marginBottom:12}}>
      <div style={S.mt}><div style={S.mV}>{journal.length}</div><div style={S.mL}>tastings</div></div>
      <div style={S.mt}><div style={S.mV}>{ag}%</div><div style={S.mL}>agreement</div></div>
      <div style={S.mt}><div style={S.mV}>{aH}</div><div style={S.mL}>his avg</div></div>
      <div style={S.mt}><div style={S.mV}>{aS}</div><div style={S.mL}>her avg</div></div>
    </div>}
    <button style={{...S.btn(true),marginBottom:12}} onClick={()=>setAdding(true)}>+ Log a tasting</button>
    {journal.length===0?<div style={S.em}><div style={{fontSize:32,marginBottom:8}}>🍷</div>Your shared journal starts here.<br/>Open a bottle and log it together.</div>
    :journal.map(e=><div key={e.id} style={{...S.cd,cursor:"default"}}>
      <div style={{display:"flex",justifyContent:"space-between"}}>
        <div><div style={{fontWeight:600,fontSize:14.5,fontFamily:"'Cormorant Garamond',serif"}}>{e.name}</div>
        <div style={{fontSize:11.5,color:"#9A8C7E",marginTop:2}}>{[e.region,e.vintage].filter(Boolean).join(" · ")} · {e.date}</div></div>
        <button onClick={()=>del(e.id)} style={{background:"none",border:"none",cursor:"pointer",color:"#9A8C7E",fontSize:15}}>×</button>
      </div>
      <div style={{display:"flex",gap:16,marginTop:8}}>
        <span style={{fontSize:11.5,color:"#6B5F55"}}>Him <Stars value={e.hisRating} size={13}/></span>
        <span style={{fontSize:11.5,color:"#6B5F55"}}>Her <Stars value={e.herRating} size={13}/></span>
      </div>
      {e.notes&&<div style={{fontSize:13,color:"#6B5F55",marginTop:8,lineHeight:1.6,fontStyle:"italic"}}>"{e.notes}"</div>}
    </div>)}
  </div>;
}

/* ═══════════ VOYAGE ═══════════ */
function VoyageMap({trips}){
  const [tip,setTip]=useState(null);
  const apps=trips.map(t=>{const a=allApps.find(x=>x.id===t.appellationId);return a?{...a,visited:t.visited}:null;}).filter(Boolean);
  if(apps.length===0)return <div style={S.em}><div style={{fontSize:30,marginBottom:8}}>🗺️</div>Save appellations to see them mapped.</div>;
  const w=400,h=250,pad=30;
  const lats=apps.map(a=>a.lat),lngs=apps.map(a=>a.lng);
  const mnLa=Math.min(...lats)-5,mxLa=Math.max(...lats)+5,mnLo=Math.min(...lngs)-8,mxLo=Math.max(...lngs)+8;
  const sc=Math.min((w-pad*2)/(mxLo-mnLo),(h-pad*2)/(mxLa-mnLa));
  const cx=(mnLo+mxLo)/2,cy=(mnLa+mxLa)/2;
  const pj=(lo,la)=>[w/2+(lo-cx)*sc,h/2-(la-cy)*sc];
  const grat=[];const st=Math.max(10,Math.round((mxLa-mnLa)/50)*10);
  for(let la=Math.floor(mnLa/st)*st;la<=mxLa;la+=st){const[x1,y1]=pj(mnLo,la),[x2,y2]=pj(mxLo,la);grat.push({x1,y1,x2,y2});}
  for(let lo=Math.floor(mnLo/st)*st;lo<=mxLo;lo+=st){const[x1,y1]=pj(lo,mnLa),[x2,y2]=pj(lo,mxLa);grat.push({x1,y1,x2,y2});}
  return <div>
    <svg viewBox={`0 0 ${w} ${h}`} style={{width:"100%",height:"auto",borderRadius:14,marginBottom:8}}>
      <rect width={w} height={h} rx={14} fill="#F5EFE6"/>
      {grat.map((l,i)=><line key={i} {...l} stroke="#E8DFD2" strokeWidth={0.4}/>)}
      {apps.map(a=>{const[x,y]=pj(a.lng,a.lat);return <g key={a.id}>
        <circle cx={x} cy={y} r={a.visited?5:7} fill={a.countryColor} opacity={a.visited?0.4:0.9} stroke="#FFFFFF" strokeWidth={1.5} style={{cursor:"pointer"}} onClick={()=>setTip(tip?.id===a.id?null:a)}/>
        {tip?.id!==a.id&&<text x={x} y={y-10} textAnchor="middle" fontSize={8}>{a.countryEmoji}</text>}
      </g>;})}
    </svg>
    {tip&&<div style={{...S.ai,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
      <div><span style={{fontSize:15,marginRight:5}}>{tip.countryEmoji}</span><span style={{fontWeight:600,fontSize:14,fontFamily:"'Cormorant Garamond',serif"}}>{tip.name}</span>
      <div style={{fontSize:11.5,color:"#9A8C7E",marginTop:2}}>{tip.regionName}, {tip.countryName}{tip.visited?" · ✓ visited":""}</div></div>
      <button style={{...S.bL,fontSize:16}} onClick={()=>setTip(null)}>×</button>
    </div>}
    <div style={{fontSize:11,color:"#9A8C7E",textAlign:"center"}}>{apps.filter(a=>a.visited).length} visited · {apps.filter(a=>!a.visited).length} to explore</div>
  </div>;
}
function VoyageTab({trips,setTrips,cache,onAddTrip}){
  const [view,setView]=useState("list");
  const [spinning,setSpinning]=useState(false);const [result,setResult]=useState(null);const ref=useRef(null);
  const del=async id=>{const u=trips.filter(t=>t.id!==id);setTrips(u);await store("wv5-trips",u);};
  const tog=async id=>{const u=trips.map(t=>t.id===id?{...t,visited:!t.visited}:t);setTrips(u);await store("wv5-trips",u);};
  const vis=trips.filter(t=>t.visited).length;
  const ctrs=[...new Set(trips.map(t=>t.countryName))].length;
  const spin=()=>{setSpinning(true);setResult(null);let c=0;const total=22+Math.floor(Math.random()*12);
    const tick=()=>{c++;setResult(allApps[Math.floor(Math.random()*allApps.length)]);if(c<total)ref.current=setTimeout(tick,55+c*13);else setSpinning(false);};tick();};
  useEffect(()=>()=>clearTimeout(ref.current),[]);
  const savedSpin=result&&trips.some(t=>t.appellationId===result.id);
  const bestVintage=result&&(()=>{const k=REGION_VINTAGE[result.regionId];if(!k)return null;const d=VINTAGES[k];const top=Object.entries(d.y).sort((a,b)=>b[1][0]-a[1][0])[0];return{year:top[0],score:top[1][0],note:top[1][1],region:d.name};})();
  return <div style={{animation:"fadeUp 0.25s ease"}}>
    <PageTitle>Voyage</PageTitle>
    {trips.length>0&&<div style={{display:"grid",gridTemplateColumns:"repeat(4,minmax(0,1fr))",gap:7,marginBottom:12}}>
      <div style={S.mt}><div style={S.mV}>{trips.length}</div><div style={S.mL}>saved</div></div>
      <div style={S.mt}><div style={S.mV}>{ctrs}</div><div style={S.mL}>countries</div></div>
      <div style={S.mt}><div style={S.mV}>{vis}</div><div style={S.mL}>visited</div></div>
      <div style={S.mt}><div style={S.mV}>{trips.length-vis}</div><div style={S.mL}>to go</div></div>
    </div>}
    <div style={S.seg}>{[["list","List"],["map","Map"],["spin","Spin 🌍"]].map(([k,l])=><button key={k} style={S.segB(view===k)} onClick={()=>setView(k)}>{l}</button>)}</div>
    {view==="map"&&<VoyageMap trips={trips}/>}
    {view==="spin"&&<div style={{textAlign:"center"}}>
      <div style={{background:"#F5EFE6",borderRadius:16,padding:"1.8rem 1.2rem",marginBottom:14,minHeight:110,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center"}}>
        {!result&&!spinning&&<div style={{fontSize:44,opacity:0.4}}>🌍</div>}
        {result&&<div><span style={{fontSize:32}}>{result.countryEmoji}</span>
          <div style={{fontSize:19,fontWeight:600,fontFamily:"'Cormorant Garamond',serif",marginTop:6}}>{result.name}</div>
          <div style={{fontSize:12,color:"#9A8C7E",marginTop:3}}>{result.regionName}, {result.countryName}</div>
          {!spinning&&<div style={{display:"flex",flexWrap:"wrap",gap:4,justifyContent:"center",marginTop:8}}>{result.grapes.map(g=><span key={g} style={S.bg(result.countryColor)}>{g}</span>)}</div>}
        </div>}
      </div>
      <button style={{...S.btn(true),marginBottom:14,opacity:spinning?0.6:1}} onClick={spin} disabled={spinning}>{spinning?"Spinning...":result?"Spin again":"Spin the globe"}</button>
      {result&&!spinning&&<div style={{textAlign:"left"}}>
        <div style={{fontSize:13,color:"#6B5F55",lineHeight:1.6,marginBottom:10}}>{result.style}</div>
        {bestVintage&&<div style={{...S.cd,cursor:"default",padding:"0.8rem 1rem"}}>
          <div style={{fontSize:10.5,fontWeight:600,color:"#9A8C7E",letterSpacing:1.5,textTransform:"uppercase",marginBottom:4}}>Best recent vintage · {bestVintage.region}</div>
          <div style={{fontSize:14}}><span style={{fontWeight:700,fontFamily:"'Cormorant Garamond',serif",fontSize:17}}>{bestVintage.year}</span> <span style={{color:vScore(bestVintage.score),fontWeight:600}}>{bestVintage.score}/5</span> <span style={{color:"#6B5F55"}}>— {bestVintage.note}</span></div>
        </div>}
        <AISec cache={cache} title="Sommelier destination brief" cacheKey={`spn-${result.id}`}
          prompt={`Landed on ${result.name} in ${result.regionName}, ${result.countryName}. JSON: {"pitch":"3-4 exciting sentences selling this wine destination","pairings":[{"dish":"specific","why":"1 sentence"}]} 3 pairings.`}/>
        {savedSpin?<div style={{textAlign:"center",fontSize:13,color:"#4E7C4E",padding:8}}>✓ Already on your list</div>
          :<button style={S.btn(false)} onClick={()=>onAddTrip({...result})}>Add to voyage list</button>}
      </div>}
    </div>}
    {view==="list"&&(trips.length===0?<div style={S.em}><div style={{fontSize:30,marginBottom:8}}>✈️</div>No appellations saved yet.<br/>Explore the Atlas or spin the globe.</div>
    :trips.map(t=><div key={t.id} style={{...S.cd,cursor:"default",opacity:t.visited?0.6:1}}>
      <div style={{display:"flex",justifyContent:"space-between"}}>
        <div style={{display:"flex",gap:10,alignItems:"center"}}><span style={{fontSize:22}}>{t.countryEmoji}</span>
          <div><div style={{fontWeight:600,fontSize:14.5,fontFamily:"'Cormorant Garamond',serif",textDecoration:t.visited?"line-through":"none"}}>{t.name}</div>
          <div style={{fontSize:11.5,color:"#9A8C7E"}}>{t.regionName}, {t.countryName}</div></div></div>
        <button onClick={()=>del(t.id)} style={{background:"none",border:"none",cursor:"pointer",color:"#9A8C7E",fontSize:15}}>×</button>
      </div>
      <div style={{display:"flex",flexWrap:"wrap",gap:4,marginTop:8}}>{t.grapes?.map(g=><span key={g} style={S.bg(t.countryColor)}>{g}</span>)}</div>
      <button onClick={()=>tog(t.id)} style={{...S.bS,width:"100%",marginTop:9,fontSize:12}}>{t.visited?"Mark unvisited":"Mark visited ✓"}</button>
    </div>))}
  </div>;
}

/* ═══════════ APP ═══════════ */
export default function WineVoyage(){
  const [tab,setTab]=useState("home");
  const [cellar,setCellar]=useState([]);
  const [journal,setJournal]=useState([]);
  const [trips,setTrips]=useState([]);
  const [taste,setTaste]=useState([]);
  const [draft,setDraft]=useState(null);
  const [loaded,setLoaded]=useState(false);
  const cache=useRef({});
  useEffect(()=>{(async()=>{
    let j=await read("wv5-journal"),t=await read("wv5-trips"),ta=await read("wv5-taste"),ce=await read("wv5-cellar");
    // one-time migration from v4
    if(!j){const old=await read("wv4-journal");if(old){j=old;await store("wv5-journal",old);}}
    if(!t){const old=await read("wv4-trips");if(old){t=old;await store("wv5-trips",old);}}
    if(!ta){const old=await read("wv4-taste");if(old){ta=old.map(x=>({id:x.id||uid(),name:x.name}));await store("wv5-taste",ta);}}
    setJournal(j||[]);setTrips(t||[]);setTaste(ta||[]);setCellar(ce||[]);setLoaded(true);
  })();},[]);
  const addTrip=async app=>{if(trips.some(t=>t.appellationId===app.id))return;
    const trip={id:uid(),appellationId:app.id,name:app.name,grapes:app.grapes,regionName:app.regionName,countryName:app.countryName,countryEmoji:app.countryEmoji,countryColor:app.countryColor,visited:false};
    const u=[...trips,trip];setTrips(u);await store("wv5-trips",u);};
  const consume=async b=>{
    const u=cellar.map(x=>x.id===b.id?{...x,qty:Math.max(0,Number(x.qty)-1)}:x);
    setCellar(u);await store("wv5-cellar",u);
    setDraft({name:`${b.producer} ${b.wine}`.trim(),region:b.appellation||"",vintage:String(b.vintage||"")});
    setTab("journal");
  };
  if(!loaded)return <div style={{background:CREAM,minHeight:"100vh"}}><div style={{...S.pg,textAlign:"center",paddingTop:"4rem"}}><div style={{fontSize:28}}>🍷</div><div style={{fontSize:13,color:"#9A8C7E",marginTop:8}}>Decanting...</div></div></div>;
  const TABS=[["home","🏠","Home"],["atlas","🌍","Atlas"],["cellar","🍾","Cellar"],["journal","📓","Journal"],["voyage","✈️","Voyage"]];
  return <div style={{background:CREAM,minHeight:"100vh"}}>
  <div style={S.pg}>
    <style>{ANIM}</style>
    <header style={S.hdr}><div style={{fontSize:10,fontWeight:600,letterSpacing:3,color:TER}}>WINE VOYAGE</div></header>
    {tab==="home"&&<HomeTab cellar={cellar} journal={journal} taste={taste} setTaste={setTaste} onConsume={consume} goTab={setTab}/>}
    {tab==="atlas"&&<AtlasTab cache={cache} trips={trips} onAddTrip={addTrip}/>}
    {tab==="cellar"&&<CellarTab cellar={cellar} setCellar={setCellar} onConsume={consume}/>}
    {tab==="journal"&&<JournalTab journal={journal} setJournal={setJournal} draft={draft} clearDraft={()=>setDraft(null)}/>}
    {tab==="voyage"&&<VoyageTab trips={trips} setTrips={setTrips} cache={cache} onAddTrip={addTrip}/>}
    <nav style={S.nav}><div style={S.navIn}>
      {TABS.map(([k,i,l])=><button key={k} style={S.navB(tab===k)} onClick={()=>setTab(k)}>
        <span style={S.navI}>{i}</span><span style={S.navL(tab===k)}>{l}</span>
      </button>)}
    </div></nav>
  </div>
  </div>;
}
