// Inline SVG charts. No library — two chart forms, drawn directly.
//
// The palette is validated, not eyeballed: #2f9fd0 (value / gain) and #e2624a
// (loss) pass the lightness band, chroma floor, CVD separation (ΔE 19.7 under
// protanopia), the normal-vision floor (ΔE 28.2), and 3:1 contrast against both
// chart surfaces. Blue rather than green for "gain" is the deliberate choice:
// a red/green pair tops out around ΔE 6 and is the classic pair red-green
// colourblind readers cannot separate. Gain and loss additionally carry a sign
// and an arrow, so colour is never the only channel.

import { el, money } from './ui.js';

export const CHART = {
  value: '#2f9fd0',   // market value, and gains
  loss: '#e2624a',    // losses
  muted: '#9a8090',   // cost basis — context, not the story
  grid: '#351e2c',
  surface: '#22111a',
};

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, value);
  }
  return node;
}

/**
 * Cellar value over time.
 *
 * Emphasis form: market value is the story and carries the accent hue; cost
 * basis is context in de-emphasis gray. Both are dollars, so they share one
 * axis — never a second y-scale.
 */
export function valueHistoryChart(points, { height = 220, currency = 'USD' } = {}) {
  const usable = points.filter((p) => p.market_value !== null || p.cost_basis !== null);
  if (usable.length < 2) {
    return el('p', { class: 'hint' },
      usable.length === 1
        ? 'One data point so far — the line starts once the cellar has been valued on a second day.'
        : 'No value history yet. Refresh valuations to record the first point.');
  }

  const width = 720;
  const pad = { top: 16, right: 64, bottom: 26, left: 56 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const values = usable.flatMap((p) => [p.market_value, p.cost_basis]).filter((v) => v !== null);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values, 0);
  // Round the top out to a clean number so the axis labels read well.
  const top = niceCeil(maxValue - minValue) + minValue;

  const times = usable.map((p) => new Date(p.date).getTime());
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const spanTime = maxTime - minTime || 1;

  const x = (date) => pad.left + ((new Date(date).getTime() - minTime) / spanTime) * plotW;
  const y = (value) => pad.top + plotH - ((value - minValue) / (top - minValue || 1)) * plotH;

  const svg = svgEl('svg', {
    viewBox: `0 0 ${width} ${height}`, class: 'chart',
    role: 'img',
    'aria-label': `Cellar value over time, ${usable.length} points, from ${usable[0].date} to ${usable.at(-1).date}`,
  });

  // Gridlines: hairline, solid, recessive — one step off the surface.
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const value = minValue + ((top - minValue) * i) / ticks;
    const yy = y(value);
    svg.append(svgEl('line', {
      x1: pad.left, x2: width - pad.right, y1: yy, y2: yy,
      stroke: CHART.grid, 'stroke-width': 1,
    }));
    const label = svgEl('text', {
      x: pad.left - 8, y: yy + 4, 'text-anchor': 'end',
      class: 'chart-tick',
    });
    label.textContent = compactMoney(value, currency);
    svg.append(label);
  }

  const series = [
    { key: 'cost_basis', color: CHART.muted, label: 'Paid', width: 2 },
    { key: 'market_value', color: CHART.value, label: 'Value', width: 2 },
  ];

  for (const line of series) {
    const path = usable
      .filter((p) => p[line.key] !== null)
      .map((p, index) => `${index ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p[line.key]).toFixed(1)}`)
      .join(' ');
    if (!path) continue;
    svg.append(svgEl('path', {
      d: path, fill: 'none', stroke: line.color,
      'stroke-width': line.width, 'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    }));

    // End marker with a surface ring, plus a direct label — sparingly, only at
    // the endpoint, so the axis and tooltip carry everything else.
    const last = [...usable].reverse().find((p) => p[line.key] !== null);
    if (!last) continue;
    svg.append(svgEl('circle', {
      cx: x(last.date), cy: y(last[line.key]), r: 4.5,
      fill: line.color, stroke: CHART.surface, 'stroke-width': 2,
    }));
    const endLabel = svgEl('text', {
      x: x(last.date) + 10, y: y(last[line.key]) + 4, class: 'chart-label',
      fill: line.color,
    });
    endLabel.textContent = compactMoney(last[line.key], currency);
    svg.append(endLabel);
  }

  // Date axis: first and last only. More would collide at this width.
  for (const [point, anchor] of [[usable[0], 'start'], [usable.at(-1), 'end']]) {
    const tick = svgEl('text', {
      x: x(point.date), y: height - 8, 'text-anchor': anchor, class: 'chart-tick',
    });
    tick.textContent = shortDate(point.date);
    svg.append(tick);
  }

  // Crosshair + tooltip.
  const hover = svgEl('line', {
    y1: pad.top, y2: pad.top + plotH, stroke: CHART.grid, 'stroke-width': 1, opacity: 0,
  });
  svg.append(hover);
  const tip = el('div', { class: 'chart-tip', hidden: true });
  const wrap = el('div', { class: 'chart-wrap' }, svg, tip);

  svg.addEventListener('pointermove', (event) => {
    const box = svg.getBoundingClientRect();
    const svgX = ((event.clientX - box.left) / box.width) * width;
    let nearest = usable[0];
    for (const point of usable) {
      if (Math.abs(x(point.date) - svgX) < Math.abs(x(nearest.date) - svgX)) nearest = point;
    }
    hover.setAttribute('x1', x(nearest.date));
    hover.setAttribute('x2', x(nearest.date));
    hover.setAttribute('opacity', 1);
    tip.hidden = false;
    tip.style.left = `${(x(nearest.date) / width) * 100}%`;
    tip.replaceChildren(
      el('div', { class: 'chart-tip-date' }, shortDate(nearest.date)),
      el('div', {}, swatch(CHART.value), ' Value ', money(nearest.market_value, currency)),
      el('div', {}, swatch(CHART.muted), ' Paid ', money(nearest.cost_basis, currency)));
  });
  svg.addEventListener('pointerleave', () => {
    hover.setAttribute('opacity', 0);
    tip.hidden = true;
  });

  return el('div', {},
    // Two series, so a legend is always present — identity is never colour alone.
    el('div', { class: 'legend' },
      el('span', {}, swatch(CHART.value), ' Market value'),
      el('span', {}, swatch(CHART.muted), ' What you paid')),
    wrap);
}

/**
 * Top movers: gain and loss against cost, diverging from a zero baseline.
 * The sign and the arrow carry the direction; colour reinforces it.
 */
export function moversChart(lots, { currency = 'USD' } = {}) {
  if (!lots.length) return el('p', { class: 'hint' }, 'No lots with both a price and a cost yet.');

  const widest = Math.max(...lots.map((lot) => Math.abs(lot.gain)), 1);
  return el('div', { class: 'movers' }, ...lots.map((lot) => {
    const up = lot.gain >= 0;
    const share = (Math.abs(lot.gain) / widest) * 50; // half-width each side of zero
    return el('div', {
      class: 'mover',
      title: `${lot.display_name}: ${money(lot.lot_value, currency)} now, ${money(lot.cost_basis, currency)} paid`,
    },
      el('span', { class: 'mover-name' }, lot.display_name),
      el('span', { class: 'mover-track' },
        el('span', {
          class: 'mover-bar',
          style: `left:${up ? 50 : 50 - share}%;width:${share}%;background:${up ? CHART.value : CHART.loss}`,
        })),
      el('span', {
        class: 'mover-value',
        style: `color:${up ? CHART.value : CHART.loss}`,
      }, `${up ? '▲' : '▼'} ${up ? '+' : '−'}${money(Math.abs(lot.gain), currency)}`,
        lot.gain_pct === null ? null : el('small', {}, ` ${up ? '+' : '−'}${Math.abs(lot.gain_pct)}%`)));
  }));
}

function swatch(color) {
  return el('i', { class: 'swatch', style: `background:${color}` });
}

function niceCeil(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}

function compactMoney(value, currency) {
  const abs = Math.abs(value);
  if (abs >= 1000) {
    return `${currency === 'USD' ? '$' : ''}${(value / 1000).toFixed(abs >= 10000 ? 0 : 1)}k`;
  }
  return money(Math.round(value), currency);
}

function shortDate(value) {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
