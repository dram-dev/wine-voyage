// Small DOM helpers. No framework: the app is a handful of views, and a build
// step would be one more thing between an edit and a deploy to Pages.

/** Create an element. `attrs.html` sets innerHTML (callers pass trusted markup);
 *  everything user-supplied goes through text children, which are escaped. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

export function mount(...nodes) {
  const main = document.getElementById('main');
  clear(main);
  main.append(...nodes.flat().filter(Boolean));
  main.focus({ preventScroll: true });
  return main;
}

export function loading(label = 'Loading…') {
  return el('div', { class: 'empty' }, el('span', { class: 'spinner' }), ' ', label);
}

export function empty(icon, title, ...rest) {
  return el('div', { class: 'empty' },
    el('span', { class: 'big' }, icon),
    el('h2', {}, title),
    ...rest);
}

export function toast(message, kind = '') {
  const host = document.getElementById('toasts');
  const node = el('div', { class: `toast ${kind}`.trim() }, message);
  host.append(node);
  setTimeout(() => node.remove(), kind === 'error' ? 6500 : 3800);
}

/** Modal dialog. Returns a close() so callers can dismiss after an action. */
export function modal(title, body, actions = []) {
  const root = document.getElementById('modal-root');
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (event) => { if (event.key === 'Escape') close(); };

  const panel = el('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    el('div', { class: 'modal-head' },
      el('h2', {}, title),
      el('button', { class: 'close', type: 'button', 'aria-label': 'Close', onClick: close }, '×')),
    body,
    actions.length ? el('div', { class: 'btn-row', style: 'margin-top:1rem' }, ...actions) : null);

  const backdrop = el('div', {
    class: 'modal-backdrop',
    onClick: (event) => { if (event.target === backdrop) close(); },
  }, panel);

  document.addEventListener('keydown', onKey);
  clear(root).append(backdrop);
  panel.querySelector('input, select, textarea, button')?.focus();
  return close;
}

export function confirmAction(title, message, confirmLabel = 'Delete') {
  return new Promise((resolve) => {
    const close = modal(title, el('p', {}, message), [
      el('button', { class: 'btn-danger', type: 'button', onClick: () => { close(); resolve(true); } }, confirmLabel),
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => { close(); resolve(false); } }, 'Cancel'),
    ]);
  });
}

export function field(label, control, hint) {
  return el('label', { class: 'field' }, el('span', {}, label), control, hint ? el('div', { class: 'hint' }, hint) : null);
}

export function select(options, value, attrs = {}) {
  const node = el('select', attrs);
  for (const option of options) {
    const [optionValue, optionLabel] = Array.isArray(option) ? option : [option, option];
    node.append(el('option', { value: optionValue, selected: String(optionValue) === String(value ?? '') }, optionLabel));
  }
  return node;
}

// ---------- formatting ----------

export function money(amount, currency = 'USD') {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) return '—';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency', currency, maximumFractionDigits: Number(amount) >= 100 ? 0 : 2,
    }).format(Number(amount));
  } catch {
    return `${currency} ${Number(amount).toFixed(2)}`;
  }
}

export function count(n) { return new Intl.NumberFormat().format(Number(n) || 0); }

export function plural(n, singular, pluralForm = `${singular}s`) {
  return `${count(n)} ${Number(n) === 1 ? singular : pluralForm}`;
}

export function date(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export const DRINK_WINDOW_LABELS = {
  ready: 'Drink now',
  hold: 'Hold',
  peak_passing: 'Drink soon',
  past: 'Past window',
  unknown: 'No window',
};

export function drinkWindowTag(status) {
  return el('span', { class: `tag ${status || 'unknown'}` }, DRINK_WINDOW_LABELS[status] || 'No window');
}

export function bars(rows, { limit = 8, label = (r) => r.key, color = null } = {}) {
  const shown = rows.slice(0, limit);
  const max = Math.max(1, ...shown.map((r) => r.bottles));
  return el('div', { class: 'bars' }, ...shown.map((row) =>
    el('div', { class: 'bar-row' },
      el('span', { class: 'label', title: String(label(row)) }, String(label(row))),
      el('span', { class: 'bar-track' },
        el('span', {
          class: 'bar-fill',
          style: `width:${(row.bottles / max) * 100}%` + (color ? `;background:${color}` : ''),
        })),
      el('span', { class: 'n' }, count(row.bottles)))));
}

/** Debounce, so typing in the search box doesn't fire a request per keystroke. */
export function debounce(fn, wait = 300) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
}
