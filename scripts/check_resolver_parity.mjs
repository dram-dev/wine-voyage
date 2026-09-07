// The resolver exists twice — server/wine_reference.py for the API, and
// web/js/reference.js so the published site autofills with no backend. They
// must agree, or the same bottle gets filed differently depending on whether a
// server happened to be reachable.
//
//   python -m scripts.dump_resolver_cases > /tmp/py.json
//   node scripts/check_resolver_parity.mjs /tmp/py.json
//
// Node has no fetch for file:// URLs, so the module's loader is shimmed here.

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const expectedPath = process.argv[2];
if (!expectedPath) {
  console.error('usage: node scripts/check_resolver_parity.mjs <python-output.json>');
  process.exit(2);
}

const realFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const href = String(url?.href ?? url);
  if (href.startsWith('file:')) {
    const body = await readFile(fileURLToPath(href), 'utf8');
    return { ok: true, json: async () => JSON.parse(body) };
  }
  return realFetch(url);
};

const { resolveLocally } = await import('../web/js/reference.js');
const expected = JSON.parse(await readFile(expectedPath, 'utf8'));

// The two sides describe the same answer with different key orders and with
// tuples vs arrays; compare the values that matter, sorted.
const shape = (r) => JSON.stringify({
  wine: Object.fromEntries(Object.entries(r.wine || {}).sort()),
  producer_match: r.producer_match ?? null,
  producer_name: r.producer_name ?? null,
  place: r.place ? { kind: r.place.kind, name: r.place.name } : null,
  typical: [...(r.typical || [])].sort(),
});

let mismatches = 0;
for (const { query, result } of expected) {
  const mine = await resolveLocally(query);
  if (shape(mine) !== shape(result)) {
    mismatches += 1;
    console.log(`MISMATCH ${JSON.stringify(query)}`);
    console.log(`   py: ${shape(result)}`);
    console.log(`   js: ${shape(mine)}`);
  }
}

console.log(`${expected.length - mismatches}/${expected.length} identical`);
process.exit(mismatches ? 1 : 0);
