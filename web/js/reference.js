// Offline wine resolution in the browser — the same algorithm as
// server/wine_reference.py, against the same data/wine_reference.json.
//
// This is what makes autofill work on the published site with no backend
// configured. It is not a stand-in for the model: it knows a few hundred
// producers and the world's common appellations, and it is deterministic and
// instant. Where a producer is unknown, the appellation or region the user
// typed still yields a country, a grape set and a drinking window.

const REFERENCE_URL = new URL('../data/wine_reference.json', import.meta.url);

const EXACT = 'exact';
const STRONG = 'strong';
const PARTIAL = 'partial';
const WEAK = 'weak';
const RANK = { exact: 0, strong: 1, partial: 2, weak: 3 };

let cache = null;
let loading = null;

/** Load once, and treat a failed fetch as "no reference" rather than an error. */
export async function loadReference() {
  if (cache) return cache;
  if (!loading) {
    loading = fetch(REFERENCE_URL)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        cache = data || { appellations: {}, aliases: {}, regions: {}, countries: {}, producers: {}, noise_words: [] };
        return cache;
      })
      .catch(() => {
        cache = { appellations: {}, aliases: {}, regions: {}, countries: {}, producers: {}, noise_words: [] };
        return cache;
      })
      .finally(() => { loading = null; });
  }
  return loading;
}

export function normalize(text) {
  if (!text) return '';
  return String(text)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')     // strip combining accents
    .replace(/[^\w\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function tokens(text, noise) {
  return normalize(text).split(' ').filter((word) => word && !noise.has(word));
}

function score(query, candidate, noise) {
  if (!query || !candidate) return null;
  if (query === candidate) return EXACT;

  const a = new Set(tokens(query, noise));
  const b = new Set(tokens(candidate, noise));
  if (!a.size || !b.size) return null;

  const order = tokens(query, noise);
  const sameSize = a.size === b.size;
  const aInB = [...a].every((word) => b.has(word));
  const bInA = [...b].every((word) => a.has(word));
  if (sameSize && aInB) return EXACT;
  // "Caymus" finds "Caymus Vineyards" — the user typed part of a longer name.
  if (aInB) return STRONG;
  // The other direction is not the same thing. Here the user typed words the
  // candidate does not have, and those words belong to *something*. Trailing
  // words are qualifiers and the match holds ("Chateau Margaux 1er" is still
  // Chateau Margaux); leading ones mean a different name is being typed
  // ("Sonoma Ridge Cellars" is not Ridge Vineyards). A winery is named
  // front-first, so the query's first significant word has to be in the match.
  if (bInA) return b.has(order[0]) ? STRONG : PARTIAL;

  const overlap = [...a].filter((word) => b.has(word));
  if (!overlap.length) return null;
  if (overlap.length / Math.max(a.size, b.size) >= 0.6) return PARTIAL;
  if (overlap.length === 1 && Math.max(...overlap.map((w) => w.length)) >= 6) return WEAK;
  return null;
}

const DEMOTE = { [EXACT]: STRONG, [STRONG]: PARTIAL, [PARTIAL]: WEAK, [WEAK]: null };

// What an entry claims about a wine's origin. Two producers resolving to the
// same appellation are interchangeable here; two that do not are a real
// ambiguity.
const identity = (entry) => entry.appellation || entry.name || '';

function best(query, table, noise) {
  const key = normalize(query);
  if (!key || !table) return [null, null];
  if (table[key]) return [table[key], EXACT];

  let bestQuality = null;
  let tied = [];
  for (const [candidateKey, entry] of Object.entries(table)) {
    const quality = score(key, candidateKey, noise);
    if (!quality) continue;
    if (!bestQuality || RANK[quality] < RANK[bestQuality]) {
      bestQuality = quality;
      tied = [entry];
    } else if (quality === bestQuality) {
      tied.push(entry);
    }
  }

  if (!bestQuality) return [null, null];
  // "Mondavi" hits two producers that both say Napa Valley — either answer is
  // the same answer. "Smith" hits six spread across Washington, Bordeaux, Napa
  // and Sonoma, and whichever one came out of the object first would be a place
  // we cannot back. Demote so the caller stops treating it as authoritative.
  if (new Set(tied.map(identity)).size > 1) {
    bestQuality = DEMOTE[bestQuality];
    if (!bestQuality) return [null, null];
  }
  return [tied[0], bestQuality];
}

function findAppellation(name, data, noise) {
  const key = normalize(name);
  if (!key) return [null, null];
  const canonical = data.aliases?.[key] || key;
  if (data.appellations?.[canonical]) return [data.appellations[canonical], EXACT];
  return best(name, data.appellations || {}, noise);
}

/**
 * Resolve everything the reference can from whatever was supplied.
 * Mirrors server/wine_reference.py `resolve`.
 */
export async function resolveLocally({ producer, vintage, appellation, region, country } = {}) {
  const data = await loadReference();
  const noise = new Set(data.noise_words || []);

  const wine = {};
  const typical = new Set();
  const [producerEntry, producerMatch] = best(producer, data.producers || {}, noise);

  // Where the user says the wine is from. Every place-ish field is tried against
  // the appellation table first: people type "Napa Valley" into the region box
  // as often as the appellation one.
  let userPlace = null;
  let userKind = null;
  for (const candidate of [appellation, region]) {
    const [entry] = findAppellation(candidate, data, noise);
    if (entry) { userPlace = entry; userKind = 'appellation'; break; }
  }
  if (!userPlace) {
    for (const candidate of [region, appellation]) {
      const [entry] = best(candidate, data.regions || {}, noise);
      if (entry) { userPlace = entry; userKind = 'region'; break; }
    }
  }

  // Where the producer says it is from. Only a confident match gets to speak:
  // an uncertain one naming an appellation is how a cellar record acquires a
  // plausible lie.
  let producerPlace = null;
  if (producerEntry && (producerMatch === EXACT || producerMatch === STRONG)) {
    [producerPlace] = findAppellation(producerEntry.appellation, data, noise);
  }

  const regionOf = (p, kind) => (kind === 'appellation' ? p.region : p.name);

  let place = null;
  let placeKind = null;
  if (!userPlace) {
    place = producerPlace;
    placeKind = producerPlace ? 'appellation' : null;
  } else if (producerPlace && regionOf(producerPlace, 'appellation') === regionOf(userPlace, userKind)) {
    // They agree on the region and the producer knows the sub-appellation:
    // "Venge Vineyards" plus a typed "Napa" is Calistoga, not Napa Valley.
    place = producerPlace;
    placeKind = 'appellation';
  } else {
    // They disagree. The user is holding the bottle; the producer table is a
    // guess about a name.
    place = userPlace;
    placeKind = userKind;
  }

  if (producerEntry && (producerMatch === EXACT || producerMatch === STRONG)) {
    wine.producer = producerEntry.name;
  }

  if (place) {
    wine.country = place.country;
    wine.region = placeKind === 'appellation' ? place.region : place.name;
    if (placeKind === 'appellation') wine.appellation = place.name;
    wine.varietals = [...place.grapes];
    wine.wine_type = place.type;
    ['varietals', 'wine_type', 'drink_from', 'drink_to'].forEach((f) => typical.add(f));
    if (vintage) {
      wine.drink_from = vintage + place.age[0];
      wine.drink_to = vintage + place.age[1];
    }
  } else {
    const [entry] = best(country, data.countries || {}, noise);
    if (entry) wine.country = entry.name;
  }

  return {
    wine,
    sources: Object.fromEntries(Object.keys(wine).map((key) => [key, 'reference'])),
    producer_match: producerEntry ? producerMatch : null,
    producer_name: producerEntry ? producerEntry.name : null,
    place: place ? { kind: placeKind, name: place.name } : null,
    typical: [...typical],
  };
}

/** Every place name the reference knows, for input autocomplete. Appellations
 *  first, then regions and countries — the order a datalist offers them in. */
export async function placeNames() {
  const data = await loadReference();
  const appellations = Object.values(data.appellations || {}).map((a) => a.name);
  const regions = Object.values(data.regions || {}).map((r) => r.name);
  const countries = Object.values(data.countries || {}).map((c) => c.name);
  const dedupe = (list) => [...new Set(list)].sort((a, b) => a.localeCompare(b));
  return { appellations: dedupe(appellations), regions: dedupe(regions), countries: dedupe(countries) };
}

/** The producer row itself, for its cuvée list. */
export async function producerEntry(name) {
  const data = await loadReference();
  const noise = new Set(data.noise_words || []);
  const [entry] = best(name, data.producers || {}, noise);
  return entry;
}

export async function referenceStats() {
  const data = await loadReference();
  return {
    producers: Object.keys(data.producers || {}).length,
    appellations: Object.keys(data.appellations || {}).length,
    regions: Object.keys(data.regions || {}).length,
  };
}
