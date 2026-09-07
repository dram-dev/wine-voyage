// In-browser sample cellar.
//
// GitHub Pages serves static files; the API runs on the user's own machine. So
// before anyone configures a backend — or when they just want to look around —
// requests are answered from this module instead. It implements the same call
// surface the real API does, over a fixed sample cellar held in memory.
//
// Writes are accepted and reflected in the UI for the session, but nothing is
// persisted: the views surface that with a "demo" badge and a warning banner.

const YEAR = new Date().getFullYear();

function wine(id, producer, name, vintage, varietals, type, country, region, appellation, from, to) {
  return {
    id, producer, wine_name: name, vintage, varietals, wine_type: type,
    country, region, appellation, appellation_id: null, bottle_size_ml: 750, abv: null,
    drink_from: from, drink_to: to, label_image_url: null,
    display_name: `${vintage || 'NV'} ${producer}${name ? ' ' + name : ''}`,
    drink_window: drinkWindow(from, to),
  };
}

function drinkWindow(from, to) {
  if (from === null && to === null) return 'unknown';
  if (from !== null && YEAR < from) return 'hold';
  if (to !== null && YEAR > to) return 'past';
  if (to !== null && YEAR >= to - 1) return 'peak_passing';
  return 'ready';
}

const WINES = [
  wine(1, 'Château Margaux', 'Grand Vin', 2015, ['Cabernet Sauvignon', 'Merlot'], 'red', 'France', 'Bordeaux', 'Margaux', 2028, 2055),
  wine(2, 'Domaine Leflaive', 'Puligny-Montrachet 1er Cru Les Pucelles', 2019, ['Chardonnay'], 'white', 'France', 'Burgundy', 'Puligny-Montrachet', 2024, 2034),
  wine(3, 'Ridge Vineyards', 'Monte Bello', 2018, ['Cabernet Sauvignon', 'Merlot', 'Petit Verdot'], 'red', 'United States', 'California', 'Santa Cruz Mountains', 2026, 2048),
  wine(4, 'Giacomo Conterno', 'Barolo Cascina Francia', 2016, ['Nebbiolo'], 'red', 'Italy', 'Piedmont', 'Barolo', 2030, 2060),
  wine(5, 'Bodegas Muga', 'Reserva', 2018, ['Tempranillo', 'Garnacha'], 'red', 'Spain', 'Rioja', 'Rioja', 2022, 2030),
  wine(6, 'Krug', 'Grande Cuvée', null, ['Chardonnay', 'Pinot Noir', 'Pinot Meunier'], 'sparkling', 'France', 'Champagne', 'Champagne', 2020, 2032),
  wine(7, 'Dr. Loosen', 'Wehlener Sonnenuhr Riesling Kabinett', 2020, ['Riesling'], 'white', 'Germany', 'Mosel', 'Mosel', 2023, 2040),
  wine(8, 'Château Musar', 'Red', 2001, ['Cabernet Sauvignon', 'Cinsault', 'Carignan'], 'red', 'Lebanon', 'Bekaa Valley', 'Bekaa Valley', 2012, 2024),
  wine(9, 'Au Bon Climat', 'Santa Barbara Pinot Noir', 2021, ['Pinot Noir'], 'red', 'United States', 'California', 'Santa Barbara County', 2023, 2029),
  wine(10, 'Quinta do Noval', 'Vintage Port', 2011, ['Touriga Nacional', 'Touriga Franca'], 'fortified', 'Portugal', 'Douro', 'Porto', 2031, 2070),
];

const SCORES = {
  1: 98, 2: 95, 3: 96, 4: 97, 5: 91, 6: 96, 7: 92, 8: 90, 9: 90, 10: 97,
};
// Sample market prices per bottle. A couple sit below what the sample cellar
// "paid" so the movers chart shows losses as well as gains.
const VALUES = {
  1: 850, 2: 320, 3: 210, 4: 260, 5: 18, 6: 195, 7: 28, 8: 30, 9: 24, 10: 120,
};

const CELLARS = [
  { id: 1, account_id: 'demo', name: 'Main Cellar', location: 'Basement, north wall', description: 'The long-haul bottles.', capacity: 400, is_default: true, created_at: '2024-01-04T00:00:00Z', updated_at: '2024-01-04T00:00:00Z' },
  { id: 2, account_id: 'demo', name: 'Kitchen Rack', location: 'Beside the pantry', description: 'Drink-now bottles within arm’s reach.', capacity: 24, is_default: false, created_at: '2024-02-11T00:00:00Z', updated_at: '2024-02-11T00:00:00Z' },
  { id: 3, account_id: 'demo', name: 'Offsite Storage', location: 'Domaine Wine Storage, unit 41', description: 'Cases bought on release.', capacity: 600, is_default: false, created_at: '2024-06-20T00:00:00Z', updated_at: '2024-06-20T00:00:00Z' },
];

// [id, cellar, wine, qty, bin, price, purchased]
const BOTTLE_ROWS = [
  [1, 1, 1, 3, 'A-01', 720, '2018-05-02'],
  [2, 1, 3, 12, 'A-04', 165, '2021-11-18'],
  [3, 1, 4, 6, 'B-02', 195, '2020-03-09'],
  [4, 1, 10, 6, 'B-07', 95, '2014-10-01'],
  [5, 1, 8, 2, 'C-03', 42, '2015-08-22'],
  [6, 2, 5, 4, 'K-1', 22, '2023-04-15'],
  [7, 2, 9, 3, 'K-2', 30, '2023-09-02'],
  [8, 2, 7, 5, 'K-3', 25, '2022-06-11'],
  [9, 3, 2, 6, 'Case 12', 295, '2022-01-30'],
  [10, 3, 6, 9, 'Case 03', 175, '2021-12-14'],
  [11, 3, 1, 9, 'Case 01', 700, '2018-05-02'],
];

function buildBottles() {
  return BOTTLE_ROWS.map(([id, cellarId, wineId, quantity, bin, price, purchased]) => ({
    id, cellar_id: cellarId, cellar_name: CELLARS.find((c) => c.id === cellarId).name,
    quantity, bin, purchase_price: price, purchase_date: purchased,
    purchase_source: null, currency: 'USD', my_rating: null, notes: null,
    status: 'in_cellar', created_at: purchased + 'T00:00:00Z', updated_at: purchased + 'T00:00:00Z',
    wine: WINES.find((w) => w.id === wineId),
    best_score: { score: SCORES[wineId], source: 'Sample data', source_kind: 'critic' },
    value: { low: VALUES[wineId] * 0.8, mid: VALUES[wineId], high: VALUES[wineId] * 1.3,
             currency: 'USD', source: 'Sample data', source_kind: 'market', estimated: false },
    lot_value: VALUES[wineId] * quantity,
  }));
}

// Mutable for the session so add/drink/move feel real while browsing.
let bottles = buildBottles();
let cellars = CELLARS.map((c) => ({ ...c }));
let nextBottleId = 100;

const SORTS = {
  added: (b) => b.created_at,
  vintage: (b) => b.wine.vintage ?? 0,
  producer: (b) => b.wine.producer.toLowerCase(),
  name: (b) => b.wine.display_name.toLowerCase(),
  varietal: (b) => (b.wine.varietals[0] || '').toLowerCase(),
  region: (b) => (b.wine.region || b.wine.country || '').toLowerCase(),
  country: (b) => (b.wine.country || '').toLowerCase(),
  quantity: (b) => b.quantity,
  price: (b) => b.purchase_price ?? null,
  value: (b) => b.value?.mid ?? null,
  score: (b) => b.best_score?.score ?? null,
  my_rating: (b) => b.my_rating ?? null,
  drink_from: (b) => b.wine.drink_from ?? null,
  bin: (b) => (b.bin || '').toLowerCase(),
};

function matches(bottle, q) {
  const haystack = [
    bottle.wine.producer, bottle.wine.wine_name, bottle.wine.region,
    bottle.wine.country, bottle.wine.appellation, bottle.bin, ...bottle.wine.varietals,
  ].filter(Boolean).join(' ').toLowerCase();
  return haystack.includes(q.toLowerCase());
}

function filterBottles(query) {
  const q = query.q?.trim();
  return bottles.filter((b) => {
    if (b.status !== (query.status || 'in_cellar')) return false;
    if (b.quantity <= 0) return false;
    if (query.cellar_id && b.cellar_id !== Number(query.cellar_id)) return false;
    if (q && !matches(b, q)) return false;
    if (query.vintage_min && (b.wine.vintage ?? 0) < Number(query.vintage_min)) return false;
    if (query.vintage_max && (b.wine.vintage ?? 9999) > Number(query.vintage_max)) return false;
    if (query.varietal && !b.wine.varietals.some((v) => v.toLowerCase() === String(query.varietal).toLowerCase())) return false;
    if (query.country && (b.wine.country || '').toLowerCase() !== String(query.country).toLowerCase()) return false;
    if (query.region && (b.wine.region || '').toLowerCase() !== String(query.region).toLowerCase()) return false;
    if (query.producer && !b.wine.producer.toLowerCase().includes(String(query.producer).toLowerCase())) return false;
    if (query.wine_type && b.wine.wine_type !== query.wine_type) return false;
    if (query.bin && b.bin !== query.bin) return false;
    if (query.drink_window && b.wine.drink_window !== query.drink_window) return false;
    if (query.min_score && (b.best_score?.score ?? -1) < Number(query.min_score)) return false;
    if (query.min_price && (b.purchase_price ?? -1) < Number(query.min_price)) return false;
    if (query.max_price && (b.purchase_price ?? Infinity) > Number(query.max_price)) return false;
    return true;
  });
}

function sortBottles(rows, sort, order) {
  const key = SORTS[sort] || SORTS.added;
  const sign = order === 'asc' ? 1 : -1;
  // Nulls last in both directions, matching the server's NULLS LAST ordering.
  return [...rows].sort((a, b) => {
    const av = key(a); const bv = key(b);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    if (av < bv) return -sign;
    if (av > bv) return sign;
    return 0;
  });
}

function tally(rows, keyFn) {
  const counts = new Map();
  for (const bottle of rows) {
    for (const key of [keyFn(bottle)].flat()) {
      if (key === null || key === undefined || key === '') continue;
      counts.set(key, (counts.get(key) || 0) + bottle.quantity);
    }
  }
  return [...counts.entries()].map(([key, count]) => ({ key, bottles: count }))
    .sort((a, b) => b.bottles - a.bottles || String(a.key).localeCompare(String(b.key)));
}

const DEMO_SUGGESTIONS = [
  { producer: 'Domaine Armand Rousseau', wine_name: 'Gevrey-Chambertin', varietals: ['Pinot Noir'], country: 'France', region: 'Burgundy', wine_type: 'red', typical_price_usd: 320, because: 'You hold serious Bordeaux and Barolo but no red Burgundy — this is the reference point.' },
  { producer: 'Produttori del Barbaresco', wine_name: 'Barbaresco', varietals: ['Nebbiolo'], country: 'Italy', region: 'Piedmont', wine_type: 'red', typical_price_usd: 45, because: 'Same grape as your Conterno Barolo at a fifth of the price — good for weeknights.' },
  { producer: 'Ceritas', wine_name: 'Sonoma Coast Chardonnay', varietals: ['Chardonnay'], country: 'United States', region: 'California', wine_type: 'white', typical_price_usd: 70, because: 'Bridges your Leflaive white Burgundy and your California reds.' },
  { producer: 'Chateau Musar', wine_name: 'White', varietals: ['Obaideh', 'Merwah'], country: 'Lebanon', region: 'Bekaa Valley', wine_type: 'white', typical_price_usd: 55, because: 'You already drink the Musar red; the white is the same house, wholly different wine.' },
  { producer: 'Emidio Pepe', wine_name: 'Montepulciano d’Abruzzo', varietals: ['Montepulciano'], country: 'Italy', region: 'Abruzzo', wine_type: 'red', typical_price_usd: 90, because: 'Ages like your Barolo but from a region your cellar is missing entirely.' },
  { producer: 'Vilmart & Cie', wine_name: 'Grand Cellier', varietals: ['Chardonnay', 'Pinot Noir'], country: 'France', region: 'Champagne', wine_type: 'sparkling', typical_price_usd: 85, because: 'Grower Champagne next to your Krug — same table, different argument.' },
];

/** Serve one API call from the sample cellar. Mirrors api.js paths exactly. */
export async function demoRequest(method, path, { query = {}, body = null } = {}) {
  await new Promise((resolve) => setTimeout(resolve, 120)); // keep loading states honest

  if (path === '/health') return { status: 'ok', demo: true };

  if (path === '/api/cellars' && method === 'GET') {
    return cellars.map((cellar) => {
      const inside = bottles.filter((b) => b.cellar_id === cellar.id && b.status === 'in_cellar');
      const vintages = inside.map((b) => b.wine.vintage).filter(Boolean);
      return {
        ...cellar,
        bottle_count: inside.reduce((sum, b) => sum + b.quantity, 0),
        lot_count: inside.length,
        total_cost: inside.reduce((sum, b) => sum + (b.purchase_price || 0) * b.quantity, 0),
        oldest_vintage: vintages.length ? Math.min(...vintages) : null,
        newest_vintage: vintages.length ? Math.max(...vintages) : null,
      };
    });
  }

  if (path === '/api/cellars' && method === 'POST') {
    const cellar = {
      id: Math.max(0, ...cellars.map((c) => c.id)) + 1, account_id: 'demo',
      name: body.name, location: body.location || null, description: body.description || null,
      capacity: body.capacity || null, is_default: !cellars.length,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      bottle_count: 0, lot_count: 0, total_cost: 0, oldest_vintage: null, newest_vintage: null,
    };
    cellars.push(cellar);
    return cellar;
  }

  const valueMatch = path.match(/^\/api\/cellars\/(\d+)\/(value|revalue)$/);
  if (valueMatch) {
    const id = Number(valueMatch[1]);
    if (valueMatch[2] === 'revalue') {
      return { priced: 0, failed: 0, attempted: 0, wines_in_cellar: bottles.length,
               message: 'Demo mode: the sample cellar is already priced.' };
    }
    return demoValueReport(id);
  }

  const cellarMatch = path.match(/^\/api\/cellars\/(\d+)(\/stats)?$/);
  if (cellarMatch) {
    const id = Number(cellarMatch[1]);
    const cellar = cellars.find((c) => c.id === id);
    if (!cellar) throw new Error('cellar not found');

    if (cellarMatch[2]) {
      const inside = bottles.filter((b) => b.cellar_id === id && b.status === 'in_cellar');
      const bottleCount = inside.reduce((sum, b) => sum + b.quantity, 0);
      const vintages = inside.map((b) => b.wine.vintage).filter(Boolean);
      const prices = inside.map((b) => b.purchase_price).filter((p) => p !== null);
      return {
        cellar,
        bottle_count: bottleCount,
        lot_count: inside.length,
        producer_count: new Set(inside.map((b) => b.wine.producer)).size,
        total_cost: inside.reduce((sum, b) => sum + (b.purchase_price || 0) * b.quantity, 0),
        avg_bottle_cost: prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null,
        market_value: inside.reduce((sum, b) => sum + (b.value?.mid || 0) * b.quantity, 0),
        valued_wines: inside.length,
        oldest_vintage: vintages.length ? Math.min(...vintages) : null,
        newest_vintage: vintages.length ? Math.max(...vintages) : null,
        capacity: cellar.capacity,
        capacity_used_pct: cellar.capacity ? Math.round((1000 * bottleCount) / cellar.capacity) / 10 : null,
        consumed_last_year: 14,
        by_type: tally(inside, (b) => b.wine.wine_type || 'unknown'),
        by_varietal: tally(inside, (b) => b.wine.varietals),
        by_vintage: tally(inside, (b) => b.wine.vintage).sort((a, b) => a.key - b.key),
        by_region: tally(inside, (b) => b.wine.region || b.wine.country || 'Unknown'),
        by_drink_window: tally(inside, (b) => b.wine.drink_window),
      };
    }
    if (method === 'PATCH') { Object.assign(cellar, body); return cellar; }
    if (method === 'DELETE') {
      cellars = cellars.filter((c) => c.id !== id);
      bottles = bottles.filter((b) => b.cellar_id !== id);
      return null;
    }
  }

  if (path === '/api/bottles' && method === 'GET') {
    const filtered = filterBottles(query);
    const sorted = sortBottles(filtered, query.sort || 'added', query.order || 'desc');
    const offset = Number(query.offset) || 0;
    const limit = Number(query.limit) || 100;
    return {
      total: filtered.length, limit, offset,
      sort: query.sort || 'added', order: query.order || 'desc',
      bottles: sorted.slice(offset, offset + limit),
    };
  }

  if (path === '/api/bottles/facets') {
    const scope = filterBottles({ cellar_id: query.cellar_id, status: query.status });
    return {
      varietals: tally(scope, (b) => b.wine.varietals),
      countries: tally(scope, (b) => b.wine.country),
      regions: tally(scope, (b) => b.wine.region),
      producers: tally(scope, (b) => b.wine.producer),
      wine_types: tally(scope, (b) => b.wine.wine_type),
      vintages: tally(scope, (b) => b.wine.vintage).sort((a, b) => b.key - a.key),
      bins: tally(scope, (b) => b.bin).sort((a, b) => String(a.key).localeCompare(String(b.key))),
      sorts: Object.keys(SORTS).sort(),
      drink_windows: ['hold', 'past', 'peak_passing', 'ready', 'unknown'],
    };
  }

  if (path === '/api/bottles' && method === 'POST') {
    const w = body.wine;
    const wineRow = {
      id: Math.max(0, ...WINES.map((x) => x.id)) + 1,
      ...w,
      varietals: w.varietals || [],
      display_name: `${w.vintage || 'NV'} ${w.producer}${w.wine_name ? ' ' + w.wine_name : ''}`,
      drink_window: drinkWindow(w.drink_from ?? null, w.drink_to ?? null),
    };
    const cellar = cellars.find((c) => c.id === Number(body.cellar_id));
    const bottle = {
      id: nextBottleId++, cellar_id: Number(body.cellar_id), cellar_name: cellar?.name || 'Cellar',
      quantity: body.quantity || 1, bin: body.bin || null,
      purchase_price: body.purchase_price ?? null, purchase_date: body.purchase_date || null,
      purchase_source: body.purchase_source || null, currency: body.currency || 'USD',
      my_rating: body.my_rating ?? null, notes: body.notes || null, status: 'in_cellar',
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      wine: wineRow, best_score: null, value: null,
    };
    bottles.push(bottle);
    return bottle;
  }

  const bottleMatch = path.match(/^\/api\/bottles\/(\d+)(\/consume|\/move)?$/);
  if (bottleMatch) {
    const id = Number(bottleMatch[1]);
    const bottle = bottles.find((b) => b.id === id);
    if (!bottle) throw new Error('bottle not found');

    if (bottleMatch[2] === '/consume') {
      bottle.quantity = Math.max(0, bottle.quantity - (body.quantity || 1));
      if (body.my_rating !== null && body.my_rating !== undefined) bottle.my_rating = body.my_rating;
      return { ...bottle, remaining: bottle.quantity };
    }
    if (bottleMatch[2] === '/move') {
      const target = cellars.find((c) => c.id === Number(body.to_cellar_id));
      const moving = body.quantity || bottle.quantity;
      bottle.quantity -= moving;
      const moved = { ...bottle, id: nextBottleId++, cellar_id: target.id, cellar_name: target.name, quantity: moving, bin: body.bin || null };
      bottles.push(moved);
      if (bottle.quantity <= 0) bottles = bottles.filter((b) => b.id !== id);
      return { moved: moving, remaining: Math.max(0, bottle.quantity), bottle: moved };
    }
    if (method === 'GET') {
      return { ...bottle, history: [
        { event_type: 'added', quantity_delta: bottle.quantity, note: bottle.purchase_source, occurred_at: bottle.created_at },
      ] };
    }
    if (method === 'PATCH') { Object.assign(bottle, body); return bottle; }
    if (method === 'DELETE') { bottles = bottles.filter((b) => b.id !== id); return null; }
  }

  if (path === '/api/labels/identify') {
    return {
      cached: false, image_sha256: 'demo',
      wine: {
        producer: 'Ridge Vineyards', wine_name: 'Monte Bello', vintage: 2018,
        varietals: ['Cabernet Sauvignon', 'Merlot', 'Petit Verdot'], wine_type: 'red',
        country: 'United States', region: 'California', appellation: 'Santa Cruz Mountains',
        bottle_size_ml: 750, abv: 13.5, drink_from: 2026, drink_to: 2048,
      },
      readable: true, confidence: 0.92,
      field_confidence: { producer: 0.97, vintage: 0.9, region: 0.85 },
      estimated_value: { low: 180, mid: 215, high: 275, currency: 'USD', estimated: true },
      notes: 'Demo mode returns a fixed result — connect your API to read real labels.',
      needs_review: true,
    };
  }

  const scoreMatch = path.match(/^\/api\/wines\/(\d+)\/(scores|valuation|similar)$/);
  if (scoreMatch) {
    const wineId = Number(scoreMatch[1]);
    const w = WINES.find((x) => x.id === wineId) || WINES[0];
    if (scoreMatch[2] === 'scores') {
      const base = SCORES[wineId] || 90;
      return {
        wine: w,
        scores: [
          { source: 'Sample critic A', source_kind: 'critic', score: base, scale: '100', reviewer: 'Demo', review: 'Sample data — connect the API for real score comparison.', url: null, confidence: null, estimated: false, fetched_at: new Date().toISOString() },
          { source: 'Sample critic B', source_kind: 'critic', score: base - 2, scale: '100', reviewer: 'Demo', review: null, url: null, confidence: null, estimated: false, fetched_at: new Date().toISOString() },
          { source: 'Sample community', source_kind: 'community', score: base - 3, scale: '100', reviewer: null, review: null, url: null, confidence: null, estimated: false, fetched_at: new Date().toISOString() },
        ],
        consensus: base - 1.7, has_live_sources: false,
        disclaimer: 'Demo mode: these are made-up numbers for layout purposes.',
      };
    }
    if (scoreMatch[2] === 'valuation') {
      const mid = VALUES[wineId] || 50;
      return {
        wine: w,
        valuations: [{ source: 'Sample market', source_kind: 'market', low: mid * 0.8, mid, high: mid * 1.3, currency: 'USD', note: 'Sample data.', confidence: null, estimated: false, fetched_at: new Date().toISOString() }],
        best: { source: 'Sample market', source_kind: 'market', low: mid * 0.8, mid, high: mid * 1.3, currency: 'USD', estimated: false },
        has_live_sources: false,
        disclaimer: 'Demo mode: these are made-up numbers for layout purposes.',
      };
    }
    return { wine: w, suggestions: DEMO_SUGGESTIONS.map((s) => ({ ...s, already_owned: false })) };
  }

  const manualValue = path.match(/^\/api\/wines\/(\d+)\/valuation$/);
  if (manualValue && method === 'PUT') {
    const wineId = Number(manualValue[1]);
    VALUES[wineId] = body.mid;
    for (const bottle of bottles) {
      if (bottle.wine.id === wineId) {
        bottle.value = { low: body.low ?? body.mid * 0.8, mid: body.mid, high: body.high ?? body.mid * 1.3,
                         currency: 'USD', source: 'Owner', source_kind: 'manual', estimated: false };
        bottle.lot_value = body.mid * bottle.quantity;
      }
    }
    return { wine_id: wineId, valuations: [{ source: 'Owner', source_kind: 'manual',
             low: body.low, mid: body.mid, high: body.high, currency: 'USD',
             estimated: false, fetched_at: new Date().toISOString() }] };
  }

  if (path === '/api/recommendations') {
    return {
      based_on: { bottle_lots: bottles.length, top_varietals: ['Cabernet Sauvignon', 'Nebbiolo', 'Chardonnay'], taste_profile_entries: 0 },
      suggestions: DEMO_SUGGESTIONS.map((s) => ({ ...s, already_owned: false })),
    };
  }

  throw new Error(`Demo mode does not implement ${method} ${path}`);
}

/** Value report over the sample cellar, including a synthesised 90-day history
 *  so the value chart has something real-shaped to draw. */
function demoValueReport(cellarId) {
  const inside = bottles.filter((b) => b.cellar_id === cellarId && b.status === 'in_cellar' && b.quantity > 0);
  const lots = inside.map((b) => {
    const lotValue = round2((b.value?.mid || 0) * b.quantity);
    const costBasis = b.purchase_price === null ? null : round2(b.purchase_price * b.quantity);
    return {
      bottle_id: b.id, wine_id: b.wine.id, display_name: b.wine.display_name,
      region: b.wine.region, country: b.wine.country, varietals: b.wine.varietals,
      bin: b.bin, quantity: b.quantity,
      unit_value: b.value?.mid ?? null, unit_cost: b.purchase_price,
      lot_value: lotValue, cost_basis: costBasis,
      gain: costBasis === null ? 0 : round2(lotValue - costBasis),
      gain_pct: costBasis ? Math.round((1000 * (lotValue - costBasis)) / costBasis) / 10 : null,
      value_kind: b.value?.source_kind || 'market', value_source: b.value?.source || 'Sample data',
      estimated: b.value?.source_kind === 'ai_estimate',
      valued_at: new Date().toISOString(),
    };
  });

  const marketValue = round2(lots.reduce((sum, l) => sum + l.lot_value, 0));
  const costBasis = round2(inside.reduce((sum, b) => sum + (b.purchase_price || 0) * b.quantity, 0));
  const bottleCount = inside.reduce((sum, b) => sum + b.quantity, 0);
  const movable = lots.filter((l) => l.cost_basis !== null).sort((a, b) => b.gain - a.gain);

  // A gently rising series with a wobble, so the chart shows a real shape.
  const history = [];
  for (let daysAgo = 90; daysAgo >= 0; daysAgo -= 10) {
    const point = new Date();
    point.setDate(point.getDate() - daysAgo);
    const progress = (90 - daysAgo) / 90;
    const wobble = 1 + Math.sin(daysAgo / 11) * 0.015;
    history.push({
      date: point.toISOString().slice(0, 10),
      bottle_count: bottleCount,
      cost_basis: costBasis,
      market_value: round2(marketValue * (0.86 + 0.14 * progress) * wobble),
      valued_bottles: bottleCount,
    });
  }
  history[history.length - 1].market_value = marketValue;

  const group = (keyFn) => {
    const map = new Map();
    for (const lot of lots) {
      const key = keyFn(lot);
      const bucket = map.get(key) || { key, value: 0, bottles: 0 };
      bucket.value = round2(bucket.value + lot.lot_value);
      bucket.bottles += lot.quantity;
      map.set(key, bucket);
    }
    return [...map.values()].sort((a, b) => b.value - a.value).slice(0, 15);
  };

  const cellar = cellars.find((c) => c.id === cellarId);
  return {
    cellar: { id: cellarId, name: cellar?.name || 'Cellar' },
    currency: 'USD',
    bottle_count: bottleCount, lot_count: lots.length,
    valued_bottles: bottleCount, valued_lots: lots.length, coverage_pct: 100,
    cost_basis: costBasis, cost_basis_priced: costBasis,
    market_value: marketValue, market_value_all: marketValue,
    market_low: round2(marketValue * 0.8), market_high: round2(marketValue * 1.3),
    estimated_share_pct: 0,
    unrealized_gain: round2(marketValue - costBasis),
    unrealized_gain_pct: costBasis ? Math.round((1000 * (marketValue - costBasis)) / costBasis) / 10 : null,
    top_gainers: movable.filter((l) => l.gain > 0).slice(0, 8),
    top_losers: movable.filter((l) => l.gain < 0).reverse().slice(0, 8),
    most_valuable: [...lots].sort((a, b) => b.lot_value - a.lot_value).slice(0, 8),
    by_region: group((l) => l.region || l.country || 'Unknown'),
    by_varietal: group((l) => l.varietals[0] || 'Unspecified'),
    history,
  };
}

function round2(value) { return Math.round(value * 100) / 100; }

/** Reset the sample cellar to its starting state (used by Settings). */
export function resetDemo() {
  bottles = buildBottles();
  cellars = CELLARS.map((c) => ({ ...c }));
  nextBottleId = 100;
}
