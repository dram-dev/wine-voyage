// Settings that live in the browser: which backend to talk to, and who you are.
//
// The site is static (GitHub Pages); the API runs wherever the user runs it —
// a Mac mini over Tailscale, localhost, a VPS. So the base URL is a setting,
// not a build constant. `?api=` in the URL overrides and persists it, which
// makes a QR code or a bookmark enough to set a phone up.

const KEY_API = 'wv.apiBase';
const KEY_ACCOUNT = 'wv.accountId';
const KEY_CELLAR = 'wv.activeCellar';
const KEY_DEMO = 'wv.demo';

function readStore(key, fallback = null) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
  } catch {
    return fallback; // private mode, or storage disabled
  }
}

function writeStore(key, value) {
  try {
    if (value === null || value === undefined || value === '') localStorage.removeItem(key);
    else localStorage.setItem(key, String(value));
  } catch { /* nothing we can do; the session just won't persist */ }
}

function newAccountId() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  return 'acct-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// A `?api=` (or `?demo=1`) param applies once, then is stripped from the URL so
// the address bar stays clean and the hash router isn't confused by it.
function consumeQueryOverrides() {
  const url = new URL(window.location.href);
  const api = url.searchParams.get('api');
  const demo = url.searchParams.get('demo');
  const account = url.searchParams.get('account');
  let touched = false;

  if (api !== null) { writeStore(KEY_API, api.trim().replace(/\/+$/, '')); url.searchParams.delete('api'); touched = true; }
  if (demo !== null) { writeStore(KEY_DEMO, demo === '1' || demo === 'true' ? '1' : ''); url.searchParams.delete('demo'); touched = true; }
  if (account !== null && account.trim()) { writeStore(KEY_ACCOUNT, account.trim()); url.searchParams.delete('account'); touched = true; }

  if (touched) history.replaceState(null, '', url.pathname + url.search + url.hash);
}

consumeQueryOverrides();

export const config = {
  get apiBase() { return readStore(KEY_API, ''); },
  set apiBase(value) { writeStore(KEY_API, (value || '').trim().replace(/\/+$/, '')); },

  get accountId() {
    let id = readStore(KEY_ACCOUNT, '');
    if (!id) { id = newAccountId(); writeStore(KEY_ACCOUNT, id); }
    return id;
  },
  set accountId(value) { writeStore(KEY_ACCOUNT, (value || '').trim()); },

  get activeCellarId() {
    const raw = readStore(KEY_CELLAR, '');
    return raw ? Number(raw) : null;
  },
  set activeCellarId(value) { writeStore(KEY_CELLAR, value ?? ''); },

  get demoMode() { return readStore(KEY_DEMO, '') === '1'; },
  set demoMode(value) { writeStore(KEY_DEMO, value ? '1' : ''); },

  // With no API configured we fall back to the sample cellar so the page is
  // explorable rather than blank.
  get usingDemo() { return this.demoMode || !this.apiBase; },
};
