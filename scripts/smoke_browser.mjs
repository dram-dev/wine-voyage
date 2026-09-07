// End-to-end check of the two things a browser suite can prove and a unit test
// cannot: that a first-time user can get from the sample cellar to their own
// data, and that the autofill form tells the truth about what it filled in.
//
//   npx --yes http-server web -p 8099 -s &
//   ./run.sh &
//   node scripts/smoke_browser.mjs http://127.0.0.1:8099/index.html http://127.0.0.1:8420
//
// Playwright is expected on the machine running this; it is not a dependency of
// the app. Exits non-zero if any check fails, and treats a console error as one.

// Playwright may be installed globally rather than in this project; point
// PLAYWRIGHT_MODULE at it if `playwright` does not resolve from here.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

const SITE = process.argv[2];
const API = process.argv[3];
if (!SITE || !API) {
  console.error('usage: node scripts/smoke_browser.mjs <site-url> <api-url>');
  process.exit(2);
}
let fails = 0;
const ok = (c, m) => { console.log(`  ${c ? 'PASS' : 'FAIL'} ${m}`); if (!c) fails++; };

const browser = await chromium.launch();
const ctx = await browser.newContext();
const pg = await ctx.newPage();
const errors = [];
pg.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
pg.on('pageerror', (e) => errors.push(String(e)));
const body = () => pg.textContent('body');

console.log('=== the connect screen asks one thing ===');
await pg.goto(SITE + '#/settings');
await pg.waitForTimeout(700);
ok((await pg.textContent('#conn-status .conn-label')).includes('Sample data'), 'starts on sample wines');
ok(await pg.locator('form input').count() === 1, 'exactly one field on screen');
ok(await pg.locator('form button').count() === 1, 'exactly one button on screen');
ok(!(await body()).includes('API base URL'), 'no "API base URL" jargon');
ok((await body()).includes('Your server address'), 'the field says what it wants');
const acctVisible = await pg.locator('input[value*="-"]').first().isVisible().catch(() => false);
ok(!acctVisible, 'the account uuid is tucked away, not in your face');

console.log('=== it refuses gibberish before touching the network ===');
const input = pg.locator('form input').first();
await input.fill('my mac mini');
await pg.click('button:has-text("Connect")');
await pg.waitForTimeout(400);
ok(/does not look like an address/.test(await body()), 'nonsense is caught with a useful message');

console.log('=== connecting is one action ===');
await input.fill(API + '/api');   // the shape a copied curl line has
await pg.click('button:has-text("Connect")');
await pg.waitForTimeout(2500);
ok((await pg.textContent('#conn-status .conn-label')).includes('Connected'), 'badge flips to Connected');
ok((await pg.evaluate(() => location.hash)) === '#/dashboard', 'lands on the dashboard, not still on settings');
ok((await pg.evaluate(() => localStorage.getItem('wv.apiBase'))) === API, 'a pasted /api is normalized away');
ok(/My cellar/.test(await pg.textContent('#cellar-switcher')), 'a first cellar exists');

console.log('=== the sample wines are gone ===');
await pg.goto(SITE + '#/inventory'); await pg.reload(); await pg.waitForTimeout(1500);
ok(!(await body()).includes('Château Margaux'), 'no sample wines');
ok(!(await body()).includes('Krug'), 'none at all');

console.log('=== settings now reports state instead of asking again ===');
await pg.goto(SITE + '#/settings'); await pg.reload(); await pg.waitForTimeout(900);
ok(/Connected to/.test(await body()), 'says it is connected');
ok(/Open this on your phone/.test(await body()), 'offers the phone link');

console.log('=== autofill, and no literal "null" in the status line ===');
await pg.goto(SITE + '#/scan?manual=1'); await pg.reload(); await pg.waitForTimeout(1200);
const label = async (n) => pg.locator(`.field:has-text("${n}") input, .field:has-text("${n}") select`).first();
await (await label('Producer')).fill('Venge Vineyards');
await (await label('Vintage')).fill('2023');
await pg.waitForTimeout(2500);
ok((await (await label('Appellation')).inputValue()) === 'Calistoga', 'resolves the appellation');
const status1 = await pg.textContent('.lookup-status, form');
ok(!/\bnull\b|\bundefined\b/.test(status1), 'no null/undefined rendered into the status line');

console.log('=== a shaky producer match warns instead of asserting ===');
await pg.goto(SITE + '#/scan?manual=1'); await pg.reload(); await pg.waitForTimeout(1200);
await (await label('Producer')).fill('Smith Family Vineyards');
await (await label('Region')).fill('Oregon');
await (await label('Region')).press('Tab');
await pg.waitForTimeout(2500);
ok((await (await label('Producer')).inputValue()) === 'Smith Family Vineyards', 'the typed name is not replaced');
ok((await (await label('Region')).inputValue()) === 'Oregon', 'the typed region is not relocated');
const status2 = await body();
ok(/typical for the region/.test(status2), 'the "typical for the region" caveat is shown');
ok(!/\bnull\b|\bundefined\b/.test(await pg.textContent('form')), 'still no stray null');

console.log('=== a blend is not collapsed by a re-lookup ===');
await pg.goto(SITE + '#/scan?manual=1'); await pg.reload(); await pg.waitForTimeout(1200);
await (await label('Producer')).fill('Ridge Vineyards');
await (await label('Vintage')).fill('2018');
await pg.waitForTimeout(2500);
const first = await (await label('Varietals')).inputValue();
await (await label('Vintage')).fill('2019');        // triggers another lookup
await pg.waitForTimeout(2500);
const second = await (await label('Varietals')).inputValue();
ok(first.includes(',') , `the reference resolved a blend (${first})`);
ok(first === second, `the blend survived the second lookup (${second})`);

await browser.close();
console.log(errors.length ? `\nconsole errors:\n${errors.join('\n')}` : '\nno console errors');
if (errors.length) fails++;
console.log(fails ? `\n${fails} FAILED` : '\nALL PASS');
process.exit(fails ? 1 : 0);
