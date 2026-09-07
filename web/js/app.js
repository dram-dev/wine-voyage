// Hash router. Hash routing (not the History API) because GitHub Pages serves
// static files — a deep path like /inventory would 404 on reload, a hash never does.

import { api } from './api.js';
import { config } from './config.js';
import { state } from './state.js';
import { el, empty, mount, toast } from './ui.js';

import { dashboardView } from './views/dashboard.js';
import { inventoryView } from './views/inventory.js';
import { cellarsView } from './views/cellars.js';
import { scanView } from './views/scan.js';
import { discoverView } from './views/discover.js';
import { settingsView } from './views/settings.js';
import { valueView } from './views/value.js';

const ROUTES = {
  dashboard: dashboardView,
  inventory: inventoryView,
  value: valueView,
  cellars: cellarsView,
  scan: scanView,
  discover: discoverView,
  settings: settingsView,
};
const DEFAULT_ROUTE = 'dashboard';

/** Split '#/inventory?varietal=Merlot' into its name and its params. */
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [name, queryString = ''] = raw.split('?');
  return {
    name: name || DEFAULT_ROUTE,
    query: Object.fromEntries(new URLSearchParams(queryString)),
  };
}

export function routeQuery() { return parseHash().query; }

/** Navigate, carrying filter state in the hash so views stay linkable. */
export function navigate(hashPath, params = {}) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '' && value !== 0) search.set(key, value);
  }
  const query = search.toString();
  const target = `${hashPath}${query ? `?${query}` : ''}`;
  if (location.hash === target) render();
  else location.hash = target;
}

function markActiveNav(name) {
  for (const link of document.querySelectorAll('[data-nav]')) {
    link.classList.toggle('active', link.dataset.nav === name);
  }
}

let rendering = false;

async function render() {
  const { name } = parseHash();
  const view = ROUTES[name];
  markActiveNav(name);

  if (!view) {
    mount(empty('🍇', 'Page not found', el('a', { class: 'btn', href: '#/dashboard' }, 'Back to the dashboard')));
    return;
  }
  if (rendering) return;
  rendering = true;
  try {
    await view();
  } catch (error) {
    console.error(error);
    mount(empty('⚠️', 'Something went wrong',
      el('p', {}, error?.message || String(error)),
      el('button', { class: 'btn', type: 'button', onClick: () => render() }, 'Try again')));
  } finally {
    rendering = false;
  }
}

// ---------- persistent chrome ----------

export async function refreshCellarSwitcher() {
  const switcher = document.getElementById('cellar-switcher');
  let cellars = [];
  try {
    cellars = await state.cellars({ force: true });
  } catch {
    // The connection indicator already reports this; leave the switcher empty.
  }

  switcher.replaceChildren();
  if (!cellars.length) {
    switcher.append(el('option', { value: '' }, 'No cellars'));
    switcher.disabled = true;
    return;
  }
  switcher.disabled = false;

  const active = state.activeCellar(cellars);
  for (const cellar of cellars) {
    switcher.append(el('option', {
      value: cellar.id,
      selected: cellar.id === active.id,
    }, `${cellar.name} (${cellar.bottle_count ?? 0})`));
  }
}

export async function refreshConnection() {
  const button = document.getElementById('conn-status');
  const label = button.querySelector('.conn-label');
  button.className = 'conn';

  if (config.usingDemo) {
    button.classList.add('demo');
    label.textContent = 'Sample data';
    button.title = 'No API configured — showing the sample cellar. Click to configure.';
    return;
  }
  label.textContent = 'Connecting…';
  try {
    await api.health();
    button.classList.add('live');
    label.textContent = 'Connected';
    button.title = `Connected to ${config.apiBase}`;
  } catch (error) {
    button.classList.add('down');
    label.textContent = 'Offline';
    button.title = error.message;
  }
}

function wireChrome() {
  document.getElementById('cellar-switcher').addEventListener('change', (event) => {
    config.activeCellarId = Number(event.target.value);
    toast('Switched cellar');
    render();
  });
  document.getElementById('conn-status').addEventListener('click', () => { location.hash = '#/settings'; });
  window.addEventListener('hashchange', render);
}

async function boot() {
  wireChrome();
  if (!location.hash) location.hash = `#/${DEFAULT_ROUTE}`;
  await refreshConnection();
  await refreshCellarSwitcher();
  await render();
}

boot();
