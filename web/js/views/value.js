// The value tracker: what the cellar is worth, what it cost, and how that moved.

import { api } from '../api.js';
import { CHART, moversChart, valueHistoryChart } from '../charts.js';
import { state } from '../state.js';
import { bars, count, el, empty, loading, money, mount, plural, toast } from '../ui.js';

export async function valueView() {
  mount(loading('Valuing the cellar…'));

  const cellars = await state.cellars();
  if (!cellars.length) {
    return mount(empty('🗄️', 'No cellars yet',
      el('a', { class: 'btn btn-primary', href: '#/cellars' }, 'Create a cellar')));
  }

  const active = state.activeCellar(cellars);
  let report;
  try {
    report = await api.cellarValue(active.id);
  } catch (error) {
    toast(error.message, 'error');
    return mount(empty('⚠️', 'Could not value the cellar', el('p', {}, error.message)));
  }

  const currency = report.currency || 'USD';
  const gain = report.unrealized_gain;
  const gainPct = report.unrealized_gain_pct;
  const up = gain !== null && gain >= 0;

  const hero = el('section', { class: 'card value-hero' },
    el('div', {},
      el('div', { class: 'k' }, 'Total cellar value'),
      el('div', { class: 'hero-figure' }, money(report.market_value_all, currency)),
      report.market_low !== null
        ? el('div', { class: 'sub' },
            `Range ${money(report.market_low, currency)}–${money(report.market_high, currency)} · `
            + `${plural(report.valued_bottles, 'bottle')} valued`)
        : null),
    el('div', { class: 'value-hero-side' },
      tile('What you paid', money(report.cost_basis, currency),
        `${plural(report.bottle_count, 'bottle')} in cellar`),
      tile('Unrealized gain',
        gain === null ? '—' : `${up ? '+' : '−'}${money(Math.abs(gain), currency)}`,
        gainPct === null ? 'Needs both a price and a cost' : `${up ? '▲' : '▼'} ${Math.abs(gainPct)}% on ${money(report.cost_basis_priced, currency)}`,
        gain === null ? null : (up ? CHART.value : CHART.loss)),
      tile('Priced', `${report.coverage_pct}%`,
        `${count(report.valued_lots)} of ${count(report.lot_count)} lots`)));

  const refreshButton = el('button', {
    class: 'btn-primary', type: 'button',
    onClick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      button.replaceChildren(el('span', { class: 'spinner' }), ' Pricing…');
      try {
        const result = await api.revalue(active.id, {});
        toast(result.message, result.priced ? 'ok' : '');
        await valueView();
      } catch (error) {
        toast(error.message, 'error');
        button.disabled = false;
        button.textContent = 'Refresh valuations';
      }
    },
  }, 'Refresh valuations');

  const coverageNote = report.coverage_pct < 100
    ? el('div', { class: 'banner warn' },
        `${plural(report.bottle_count - report.valued_bottles, 'bottle')} in this cellar have no price yet, so they are missing from the total. `,
        'Refresh valuations to price them.')
    : null;

  const estimateNote = report.estimated_share_pct > 0
    ? el('p', { class: 'hint' },
        `${report.estimated_share_pct}% of this total rests on model estimates rather than real market prices. `
        + 'Enter a price you know on any bottle to override it — a manual price outranks every other source.')
    : null;

  const historyCard = el('section', { class: 'card' },
    el('h2', {}, 'Value over time'),
    el('p', { class: 'hint' },
      'A point is recorded each day you open this page, so the line fills in as you use the app.'),
    valueHistoryChart(report.history, { currency }),
    report.history.length > 1 ? historyTable(report.history, currency) : null);

  const moversCard = el('section', { class: 'card' },
    el('h2', {}, 'Biggest movers'),
    el('p', { class: 'hint' }, 'Value now against what you paid, per lot.'),
    moversChart(dedupe([...report.top_gainers.slice(0, 5), ...report.top_losers.slice(0, 5)])
      .sort((a, b) => b.gain - a.gain), { currency }));

  const valuableCard = el('section', { class: 'card' },
    el('h2', {}, 'Most valuable lots'),
    el('div', { class: 'table-scroll' },
      el('table', { class: 'plain' },
        el('thead', {}, el('tr', {},
          el('th', {}, 'Wine'), el('th', {}, 'Qty'),
          el('th', {}, 'Each'), el('th', {}, 'Lot'), el('th', {}, 'Source'))),
        el('tbody', {}, ...report.most_valuable.map((lot) => el('tr', {},
          el('td', {}, lot.display_name),
          el('td', {}, String(lot.quantity)),
          el('td', {}, money(lot.unit_value, currency)),
          el('td', {}, money(lot.lot_value, currency)),
          el('td', {}, lot.estimated
            ? el('span', { class: 'tag estimate' }, 'estimate')
            : el('span', { class: 'tag' }, lot.value_kind === 'manual' ? 'yours' : 'market'))))))));

  const breakdowns = el('div', { class: 'stat-grid' },
    el('section', { class: 'card' }, el('h3', {}, 'Value by region'),
      bars(report.by_region.map((r) => ({ key: r.key, bottles: r.value })),
        { label: (r) => r.key, color: CHART.value })),
    el('section', { class: 'card' }, el('h3', {}, 'Value by varietal'),
      bars(report.by_varietal.map((r) => ({ key: r.key, bottles: r.value })),
        { label: (r) => r.key, color: CHART.value })));

  return mount(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Value'),
        el('p', {}, `${active.name} · priced ${report.coverage_pct}%`)),
      el('div', { class: 'btn-row' }, refreshButton)),
    coverageNote,
    hero,
    estimateNote,
    historyCard,
    moversCard,
    valuableCard,
    breakdowns);
}

/** Gainers and losers are disjoint server-side; this keeps them disjoint if that
 *  ever changes. */
function dedupe(lots) {
  const seen = new Set();
  return lots.filter((lot) => !seen.has(lot.bottle_id) && seen.add(lot.bottle_id));
}

function tile(key, value, sub, color) {
  return el('div', { class: 'stat' },
    el('div', { class: 'k' }, key),
    el('div', { class: 'v', style: color ? `color:${color}` : null }, value),
    sub ? el('div', { class: 'sub' }, sub) : null);
}

/** A table view of the same series, so nothing is gated behind the chart. */
function historyTable(history, currency) {
  const details = el('details', { class: 'chart-table' },
    el('summary', {}, 'View as table'),
    el('div', { class: 'table-scroll' },
      el('table', { class: 'plain' },
        el('thead', {}, el('tr', {},
          el('th', {}, 'Date'), el('th', {}, 'Bottles'),
          el('th', {}, 'Paid'), el('th', {}, 'Value'))),
        el('tbody', {}, ...[...history].reverse().map((point) => el('tr', {},
          el('td', {}, point.date),
          el('td', {}, count(point.bottle_count)),
          el('td', {}, money(point.cost_basis, currency)),
          el('td', {}, money(point.market_value, currency))))))));
  return details;
}
