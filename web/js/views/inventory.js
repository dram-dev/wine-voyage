// The inventory browser: search, filter, sort. Filter state lives in the URL
// hash so a filtered view is linkable and survives a reload.

import { api } from '../api.js';
import { state } from '../state.js';
import {
  bars, count, debounce, drinkWindowTag, el, empty, loading, money, mount, plural, select, toast,
} from '../ui.js';
import { bottleSheet } from './bottle.js';
import { navigate, routeQuery } from '../app.js';

const SORT_LABELS = {
  added: 'Recently added', vintage: 'Vintage', producer: 'Producer', name: 'Name',
  varietal: 'Varietal', region: 'Region', country: 'Country', quantity: 'Quantity',
  price: 'Price paid', value: 'Estimated value', score: 'Critic score',
  my_rating: 'My rating', drink_from: 'Drink from', bin: 'Bin',
};
const WINDOW_LABELS = {
  ready: 'Drink now', peak_passing: 'Drink soon', hold: 'Hold',
  past: 'Past window', unknown: 'No window',
};
const TYPE_LABELS = {
  red: 'Red', white: 'White', rose: 'Rosé', sparkling: 'Sparkling',
  dessert: 'Dessert', fortified: 'Fortified', other: 'Other',
};
const PAGE_SIZE = 50;

export async function inventoryView() {
  const params = routeQuery();
  mount(loading('Searching the cellar…'));

  const cellars = await state.cellars();
  if (!cellars.length) {
    return mount(empty('🗄️', 'No cellars yet',
      el('p', {}, 'Create a cellar before adding bottles.'),
      el('a', { class: 'btn btn-primary', href: '#/cellars' }, 'Create a cellar')));
  }

  const allCellars = params.scope === 'all';
  const active = state.activeCellar(cellars);
  const scopeCellarId = allCellars ? null : active.id;

  const query = {
    cellar_id: scopeCellarId,
    q: params.q || '',
    varietal: params.varietal || '',
    country: params.country || '',
    region: params.region || '',
    wine_type: params.wine_type || '',
    drink_window: params.drink_window || '',
    vintage_min: params.vintage_min || '',
    vintage_max: params.vintage_max || '',
    min_score: params.min_score || '',
    bin: params.bin || '',
    sort: params.sort || 'added',
    order: params.order || (params.sort && params.sort !== 'added' ? 'asc' : 'desc'),
    limit: PAGE_SIZE,
    offset: Number(params.offset) || 0,
  };

  let results;
  let facets;
  try {
    [results, facets] = await Promise.all([
      api.searchBottles(query),
      api.facets({ cellar_id: scopeCellarId }),
    ]);
  } catch (error) {
    toast(error.message, 'error');
    return mount(empty('⚠️', 'Search failed', el('p', {}, error.message)));
  }

  const update = (changes) => navigate('#/inventory', { ...params, offset: 0, ...changes });

  // --- toolbar ---
  const searchBox = el('input', {
    type: 'search', value: query.q, placeholder: 'Search producer, cuvée, region, varietal, bin…',
    'aria-label': 'Search the cellar',
    onInput: debounce((event) => update({ q: event.target.value }), 350),
  });

  const sortSelect = select(
    Object.entries(SORT_LABELS).filter(([key]) => !facets.sorts || facets.sorts.includes(key)),
    query.sort,
    { 'aria-label': 'Sort by', onChange: (event) => update({ sort: event.target.value }) },
  );

  const orderButton = el('button', {
    type: 'button', title: query.order === 'asc' ? 'Ascending' : 'Descending',
    onClick: () => update({ order: query.order === 'asc' ? 'desc' : 'asc' }),
  }, query.order === 'asc' ? '↑ Asc' : '↓ Desc');

  const scopeButton = el('button', {
    type: 'button',
    onClick: () => update({ scope: allCellars ? '' : 'all' }),
  }, allCellars ? `All cellars` : active.name);

  const activeFilters = ['varietal', 'country', 'region', 'wine_type', 'drink_window', 'vintage_min', 'vintage_max', 'min_score', 'bin']
    .filter((key) => query[key]);

  const filterPanel = el('div', { class: 'card filter-panel' + (activeFilters.length ? ' open' : '') },
    filterGroup('Varietal', facets.varietals, query.varietal, (v) => update({ varietal: v })),
    filterGroup('Region', facets.regions, query.region, (v) => update({ region: v })),
    filterGroup('Country', facets.countries, query.country, (v) => update({ country: v })),
    filterGroup('Type', facets.wine_types, query.wine_type, (v) => update({ wine_type: v }), (k) => TYPE_LABELS[k] || k),
    filterGroup('Drink window', (facets.drink_windows || []).map((k) => ({ key: k, bottles: null })),
      query.drink_window, (v) => update({ drink_window: v }), (k) => WINDOW_LABELS[k] || k),
    facets.bins?.length ? filterGroup('Bin', facets.bins, query.bin, (v) => update({ bin: v })) : null,
    vintageRange(facets.vintages, query, update));

  const toggleFilters = el('button', {
    type: 'button', 'aria-expanded': String(filterPanel.classList.contains('open')),
    onClick: (event) => {
      const open = filterPanel.classList.toggle('open');
      event.currentTarget.setAttribute('aria-expanded', String(open));
    },
  }, `⚙ Filters${activeFilters.length ? ` (${activeFilters.length})` : ''}`);

  const toolbar = el('div', { class: 'toolbar' },
    el('div', { class: 'toolbar-row' },
      el('div', { class: 'grow' }, searchBox),
      scopeButton, toggleFilters, sortSelect, orderButton),
    activeFilters.length
      ? el('div', { class: 'chip-row' },
          ...activeFilters.map((key) => el('button', {
            class: 'chip on', type: 'button', onClick: () => update({ [key]: '' }),
          }, `${filterLabel(key)}: ${filterValue(key, query[key])} ×`)),
          el('button', { class: 'chip', type: 'button', onClick: () => navigate('#/inventory', { scope: params.scope || '' }) }, 'Clear all'))
      : null,
    filterPanel);

  // --- results ---
  const shown = results.bottles.length;
  const totalBottles = results.bottles.reduce((sum, b) => sum + b.quantity, 0);
  const resultLine = el('div', { class: 'result-line' },
    results.total === 0
      ? 'No bottles match.'
      : `${plural(results.total, 'lot')}${shown < results.total ? ` (showing ${count(shown)})` : ''} · ${plural(totalBottles, 'bottle')} on this page`);

  const list = results.bottles.length
    ? el('div', { class: 'bottle-list' }, ...results.bottles.map((bottle) => bottleRow(bottle, () => inventoryView())))
    : empty('🔍', 'Nothing matches',
        el('p', {}, 'Loosen a filter, or add the bottle you were looking for.'),
        el('div', { class: 'btn-row', style: 'justify-content:center' },
          el('a', { class: 'btn', href: '#/scan' }, '📷 Scan a label'),
          el('button', { class: 'btn btn-ghost', type: 'button', onClick: () => navigate('#/inventory', {}) }, 'Clear filters')));

  const pager = results.total > PAGE_SIZE
    ? el('div', { class: 'btn-row', style: 'justify-content:center;margin-top:1rem' },
        el('button', {
          type: 'button', disabled: query.offset === 0,
          onClick: () => navigate('#/inventory', { ...params, offset: Math.max(0, query.offset - PAGE_SIZE) }),
        }, '← Previous'),
        el('span', { class: 'hint', style: 'align-self:center' },
          `${count(query.offset + 1)}–${count(query.offset + shown)} of ${count(results.total)}`),
        el('button', {
          type: 'button', disabled: query.offset + PAGE_SIZE >= results.total,
          onClick: () => navigate('#/inventory', { ...params, offset: query.offset + PAGE_SIZE }),
        }, 'Next →'))
    : null;

  return mount(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Inventory'),
        el('p', {}, allCellars ? 'Every cellar on this account' : `${active.name}${active.location ? ' · ' + active.location : ''}`)),
      el('div', { class: 'btn-row' },
        el('a', { class: 'btn', href: '#/scan' }, '📷 Scan'),
        el('a', { class: 'btn btn-primary', href: '#/scan?manual=1' }, '+ Add bottle'))),
    toolbar, resultLine, list, pager);
}

function bottleRow(bottle, onChange) {
  const wine = bottle.wine;
  return el('button', {
    class: 'bottle', type: 'button',
    onClick: () => bottleSheet(bottle.id, onChange),
  },
    el('div', { class: 'qty' }, String(bottle.quantity), el('small', {}, bottle.quantity === 1 ? 'btl' : 'btls')),
    el('div', {},
      el('div', { class: 'title' }, wine.display_name),
      el('div', { class: 'meta' },
        wine.varietals.length ? el('span', {}, wine.varietals.slice(0, 3).join(', ')) : null,
        [wine.appellation, wine.region, wine.country].filter(Boolean).length
          ? el('span', {}, '· ' + [wine.appellation || wine.region, wine.country].filter(Boolean).join(', '))
          : null,
        drinkWindowTag(wine.drink_window),
        bottle.bin ? el('span', { class: 'tag' }, bottle.bin) : null,
        bottle.cellar_name ? el('span', { class: 'tag' }, bottle.cellar_name) : null)),
    el('div', { class: 'right' },
      bottle.best_score
        ? el('div', { class: 'score', title: `${bottle.best_score.source}${bottle.best_score.source_kind === 'ai_estimate' ? ' (estimated)' : ''}` },
            String(bottle.best_score.score) + (bottle.best_score.source_kind === 'ai_estimate' ? '*' : ''))
        : null,
      bottle.value ? el('div', {}, money(bottle.value.mid, bottle.value.currency)) : null,
      bottle.purchase_price ? el('div', { class: 'hint' }, `paid ${money(bottle.purchase_price, bottle.currency)}`) : null));
}

function filterGroup(title, options, current, onPick, labelFn = (k) => k) {
  if (!options?.length) return null;
  return el('div', { style: 'margin-bottom:.8rem' },
    el('div', { class: 'k', style: 'font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-faint);margin-bottom:.35rem' }, title),
    el('div', { class: 'chip-row' },
      ...options.slice(0, 14).map((option) => el('button', {
        class: 'chip' + (String(current) === String(option.key) ? ' on' : ''),
        type: 'button',
        onClick: () => onPick(String(current) === String(option.key) ? '' : option.key),
      }, labelFn(option.key) + (option.bottles !== null && option.bottles !== undefined ? ` ${option.bottles}` : '')))));
}

function vintageRange(vintages, query, update) {
  if (!vintages?.length) return null;
  const years = vintages.map((v) => Number(v.key)).filter(Boolean);
  const min = el('input', { type: 'number', value: query.vintage_min || '', placeholder: String(Math.min(...years)), min: '1800', max: '2100' });
  const max = el('input', { type: 'number', value: query.vintage_max || '', placeholder: String(Math.max(...years)), min: '1800', max: '2100' });
  const apply = () => update({ vintage_min: min.value, vintage_max: max.value });
  min.addEventListener('change', apply);
  max.addEventListener('change', apply);

  return el('div', {},
    el('div', { class: 'k', style: 'font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-faint);margin-bottom:.35rem' }, 'Vintage'),
    el('div', { style: 'display:flex;gap:.5rem;align-items:center;max-width:320px' }, min, el('span', { class: 'hint' }, 'to'), max),
    el('div', { style: 'margin-top:.6rem' }, bars(vintages.slice(0, 12), { label: (r) => String(r.key) })));
}

function filterLabel(key) {
  return { vintage_min: 'From', vintage_max: 'To', min_score: 'Score ≥', wine_type: 'Type', drink_window: 'Window' }[key]
    || key.charAt(0).toUpperCase() + key.slice(1);
}

function filterValue(key, value) {
  if (key === 'wine_type') return TYPE_LABELS[value] || value;
  if (key === 'drink_window') return WINDOW_LABELS[value] || value;
  return value;
}
