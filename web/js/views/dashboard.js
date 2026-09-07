import { api } from '../api.js';
import { config } from '../config.js';
import { state } from '../state.js';
import { bars, count, el, empty, loading, money, mount, plural, toast } from '../ui.js';

export async function dashboardView() {
  mount(loading('Reading the cellar…'));

  const cellars = await state.cellars();
  if (!cellars.length) {
    return mount(empty('🗄️', 'No cellars yet',
      el('p', {}, 'A cellar is a place you keep bottles — a basement, a rack, an offsite locker. Make one to start.'),
      el('a', { class: 'btn btn-primary', href: '#/cellars' }, 'Create a cellar')));
  }

  const active = state.activeCellar(cellars);
  let stats;
  try {
    stats = await api.cellarStats(active.id);
  } catch (error) {
    toast(error.message, 'error');
    return mount(empty('⚠️', 'Could not load stats', el('p', {}, error.message)));
  }

  const currency = 'USD';
  const gain = stats.market_value !== null && stats.total_cost
    ? stats.market_value - stats.total_cost
    : null;

  const tiles = el('div', { class: 'stat-grid' },
    tile('Bottles', count(stats.bottle_count), `${plural(stats.lot_count, 'lot')} · ${plural(stats.producer_count, 'producer')}`),
    tile('Paid', money(stats.total_cost, currency), stats.avg_bottle_cost ? `${money(stats.avg_bottle_cost, currency)} average` : null),
    tile('Estimated value', money(stats.market_value, currency),
      gain === null ? `${count(stats.valued_wines)} wines valued`
        : `${gain >= 0 ? '+' : ''}${money(gain, currency)} vs. paid`),
    tile('Capacity', stats.capacity ? `${stats.capacity_used_pct}%` : '—',
      stats.capacity ? `${count(stats.bottle_count)} of ${count(stats.capacity)}` : 'No capacity set'),
    tile('Vintages', stats.oldest_vintage ? `${stats.oldest_vintage}–${stats.newest_vintage}` : '—', 'Oldest to newest'),
    tile('Drunk this year', count(stats.consumed_last_year), 'Last 365 days'),
  );

  const drinkNow = (stats.by_drink_window.find((r) => r.key === 'ready')?.bottles || 0)
    + (stats.by_drink_window.find((r) => r.key === 'peak_passing')?.bottles || 0);
  const past = stats.by_drink_window.find((r) => r.key === 'past')?.bottles || 0;

  const readiness = el('section', { class: 'card' },
    el('h2', {}, 'Drinking window'),
    el('p', { class: 'hint' },
      `${count(drinkNow)} in window now` + (past ? ` · ${count(past)} past their window` : '')),
    stats.by_drink_window.length
      ? bars(stats.by_drink_window, { label: (r) => WINDOW_LABELS[r.key] || r.key })
      : el('p', { class: 'hint' }, 'No drink windows recorded yet.'),
    el('div', { class: 'btn-row', style: 'margin-top:.8rem' },
      el('a', { class: 'btn btn-sm', href: '#/inventory?drink_window=ready' }, 'Ready to drink'),
      el('a', { class: 'btn btn-sm', href: '#/inventory?drink_window=peak_passing' }, 'Drink soon'),
      past ? el('a', { class: 'btn btn-sm', href: '#/inventory?drink_window=past' }, 'Past window') : null,
      el('a', { class: 'btn btn-sm', href: '#/inventory?drink_window=hold' }, 'Still holding')));

  const breakdowns = el('div', { class: 'stat-grid', style: 'margin-top:.8rem' },
    breakdown('By varietal', stats.by_varietal, 'varietal'),
    breakdown('By region', stats.by_region, 'region'),
    breakdown('By type', stats.by_type, 'wine_type'),
    breakdown('By vintage', [...stats.by_vintage].reverse(), 'vintage_min'));

  return mount(
    el('div', { class: 'page-head' },
      el('div', {},
        el('h1', {}, active.name),
        el('p', {}, [active.location, active.description].filter(Boolean).join(' · ') || 'Cellar overview')),
      el('div', { class: 'btn-row' },
        el('a', { class: 'btn', href: '#/scan' }, '📷 Scan a label'),
        el('a', { class: 'btn btn-primary', href: '#/inventory' }, 'Browse inventory'))),
    config.usingDemo ? demoBanner() : null,
    tiles,
    el('div', { style: 'margin-top:.8rem' }, readiness),
    breakdowns);
}

const WINDOW_LABELS = {
  ready: 'Drink now', hold: 'Hold', peak_passing: 'Drink soon',
  past: 'Past window', unknown: 'No window',
};

function tile(key, value, sub) {
  return el('div', { class: 'stat' },
    el('div', { class: 'k' }, key),
    el('div', { class: 'v' }, value),
    sub ? el('div', { class: 'sub' }, sub) : null);
}

function breakdown(title, rows, filterKey) {
  return el('section', { class: 'card' },
    el('h3', {}, title),
    rows.length
      ? bars(rows, { limit: 7 })
      : el('p', { class: 'hint' }, 'Nothing recorded yet.'),
    rows.length > 7
      ? el('a', { class: 'hint', href: `#/inventory?sort=${filterKey === 'vintage_min' ? 'vintage' : filterKey}` },
          `+${rows.length - 7} more`)
      : null);
}

function demoBanner() {
  return el('div', { class: 'banner warn' },
    'These are sample wines — nothing you change here is saved. ',
    el('a', { href: '#/settings' }, 'Connect your cellar'),
    ' to see your own bottles.');
}
