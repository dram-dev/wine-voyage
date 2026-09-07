// Bottle detail sheet: what it is, what it's worth, what critics think, what
// else you'd like — plus the actions (drink, move, edit, remove).

import { api } from '../api.js';
import { state } from '../state.js';
import {
  confirmAction, date, drinkWindowTag, el, field, loading, modal, money, plural, select, toast,
} from '../ui.js';
import { CHART } from '../charts.js';

export async function bottleSheet(bottleId, onChange = () => {}) {
  const body = el('div', {}, loading('Loading bottle…'));
  const close = modal('Bottle', body);

  let bottle;
  try {
    bottle = await api.getBottle(bottleId);
  } catch (error) {
    body.replaceChildren(el('p', { class: 'banner error' }, error.message));
    return;
  }

  const wine = bottle.wine;
  const refresh = async () => { close(); await onChange(); };

  const facts = el('dl', { class: 'kv' },
    row('Quantity', plural(bottle.quantity, 'bottle')),
    row('Cellar', bottle.cellar_name + (bottle.bin ? ` · ${bottle.bin}` : '')),
    wine.varietals.length ? row('Varietals', wine.varietals.join(', ')) : null,
    row('Origin', [wine.appellation, wine.region, wine.country].filter(Boolean).join(', ') || '—'),
    wine.wine_type ? row('Type', wine.wine_type) : null,
    wine.bottle_size_ml !== 750 ? row('Format', `${wine.bottle_size_ml} ml`) : null,
    wine.abv ? row('ABV', `${wine.abv}%`) : null,
    row('Drink window', drinkWindowTag(wine.drink_window),
      wine.drink_from || wine.drink_to ? ` ${wine.drink_from || '?'}–${wine.drink_to || '?'}` : ''),
    bottle.purchase_price ? row('Paid', `${money(bottle.purchase_price, bottle.currency)} each`) : null,
    bottle.purchase_date ? row('Purchased', date(bottle.purchase_date)) : null,
    bottle.purchase_source ? row('From', bottle.purchase_source) : null,
    bottle.my_rating ? row('My rating', `${bottle.my_rating}/100`) : null,
    bottle.value ? row('Value',
      `${money(bottle.value.mid, bottle.value.currency)} each · ${money(bottle.value.mid * bottle.quantity, bottle.value.currency)} for the lot`,
      bottle.value.estimated ? el('span', { class: 'tag estimate', style: 'margin-left:.4rem' }, 'estimate') : null) : null,
    bottle.value && bottle.purchase_price ? row('Gain',
      valueDelta(bottle, bottle.value.currency)) : null);

  const actions = el('div', { class: 'btn-row', style: 'margin:1rem 0' },
    el('button', { class: 'btn-primary', type: 'button', onClick: () => drinkForm(bottle, refresh) }, '🍷 Drink'),
    el('button', { type: 'button', onClick: () => moveForm(bottle, refresh) }, '↔ Move'),
    el('button', { type: 'button', onClick: () => editForm(bottle, refresh) }, '✎ Edit'),
    el('button', { type: 'button', onClick: () => priceForm(bottle, refresh) }, '💰 Set price'),
    el('button', {
      class: 'btn-danger', type: 'button',
      onClick: async () => {
        const ok = await confirmAction('Remove this lot?',
          `${wine.display_name} — ${plural(bottle.quantity, 'bottle')} will be removed from ${bottle.cellar_name}.`, 'Remove');
        if (!ok) return;
        try { await api.deleteBottle(bottle.id); toast('Removed', 'ok'); await refresh(); }
        catch (error) { toast(error.message, 'error'); }
      },
    }, 'Remove'));

  const scoresBox = el('section', { class: 'card' }, el('h3', {}, 'Scores'), loading('Comparing scores…'));
  const similarBox = el('section', { class: 'card' }, el('h3', {}, 'You may also like'), loading('Thinking…'));

  const history = bottle.history?.length
    ? el('section', { class: 'card' }, el('h3', {}, 'History'),
        el('table', { class: 'plain' },
          el('tbody', {}, ...bottle.history.map((event) => el('tr', {},
            el('td', {}, date(event.occurred_at)),
            el('td', {}, event.event_type),
            el('td', {}, event.quantity_delta > 0 ? `+${event.quantity_delta}` : String(event.quantity_delta)),
            el('td', { class: 'hint' }, event.note || ''))))))
    : null;

  body.replaceChildren(
    el('div', {},
      el('h2', { style: 'margin-bottom:.2rem' }, wine.display_name),
      el('p', { class: 'hint' }, [wine.appellation || wine.region, wine.country].filter(Boolean).join(', '))),
    facts, actions, scoresBox, similarBox, history);

  loadScores(wine.id, scoresBox);
  loadSimilar(wine.id, similarBox);
}

/** Gain on this lot, with the sign and arrow carrying direction, not colour alone. */
function valueDelta(bottle, currency) {
  const delta = (bottle.value.mid - bottle.purchase_price) * bottle.quantity;
  const pct = Math.round((100 * (bottle.value.mid - bottle.purchase_price)) / bottle.purchase_price);
  const up = delta >= 0;
  return el('span', { style: `color:${up ? CHART.value : CHART.loss};font-weight:600` },
    `${up ? '▲' : '▼'} ${up ? '+' : '−'}${money(Math.abs(delta), currency)}`,
    el('small', { style: 'opacity:.8;font-weight:400' }, ` ${up ? '+' : '−'}${Math.abs(pct)}%`));
}

/** Enter a price you know. A manual price outranks the model's estimate. */
function priceForm(bottle, refresh) {
  const mid = el('input', { type: 'number', step: '0.01', min: '0', required: true,
    value: bottle.value?.mid ?? '', placeholder: 'What one bottle is worth now' });
  const low = el('input', { type: 'number', step: '0.01', min: '0', value: bottle.value?.low ?? '' });
  const high = el('input', { type: 'number', step: '0.01', min: '0', value: bottle.value?.high ?? '' });
  const note = el('input', { placeholder: 'Where the price came from' });
  const save = el('button', { class: 'btn-primary', type: 'submit' }, 'Save price');

  const close = modal(`Price ${bottle.wine.display_name}`, el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      if (!mid.value) { toast('A per-bottle value is required', 'error'); return; }
      save.disabled = true;
      try {
        await api.setValuation(bottle.wine.id, {
          mid: Number(mid.value),
          low: low.value ? Number(low.value) : null,
          high: high.value ? Number(high.value) : null,
          note: note.value.trim() || null,
        });
        toast('Price saved', 'ok');
        close();
        await refresh();
      } catch (error) { toast(error.message, 'error'); save.disabled = false; }
    },
  },
    el('p', { class: 'hint' },
      'Your own price wins over a market feed and over the model\u2019s estimate, everywhere the cellar is valued.'),
    el('div', { class: 'field-grid' },
      field('Per bottle *', mid), field('Low', low), field('High', high)),
    field('Note', note),
    el('div', { class: 'btn-row' }, save,
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => close() }, 'Cancel'))));
}

function row(key, ...value) {
  return [el('dt', {}, key), el('dd', {}, ...value.filter((v) => v !== undefined && v !== ''))];
}

async function loadScores(wineId, box) {
  try {
    const data = await api.scores(wineId);
    const parts = [el('h3', {}, 'Scores')];

    if (!data.scores.length) {
      parts.push(el('p', { class: 'hint' }, 'No scores on file for this wine yet.'),
        el('button', {
          class: 'btn-sm', type: 'button',
          onClick: (event) => { event.target.disabled = true; box.replaceChildren(el('h3', {}, 'Scores'), loading('Looking it up…')); loadScores(wineId, box, true); },
        }, 'Look one up'));
    } else {
      if (data.consensus) {
        parts.push(el('p', { class: 'hint' }, `Consensus ${data.consensus} across ${plural(data.scores.length, 'source')}.`));
      }
      for (const score of data.scores) {
        parts.push(el('div', { class: 'score-row' },
          el('div', {},
            el('div', { class: 'src' }, score.source,
              score.estimated ? el('span', { class: 'tag estimate', style: 'margin-left:.4rem' }, 'estimate') : null),
            score.review ? el('div', { class: 'rev' }, score.review) : null),
          el('div', { class: 'n' }, score.score === null ? '—' : String(score.score))));
      }
    }
    if (data.disclaimer) parts.push(el('p', { class: 'hint', style: 'margin-top:.7rem' }, data.disclaimer));
    box.replaceChildren(...parts);
  } catch (error) {
    box.replaceChildren(el('h3', {}, 'Scores'), el('p', { class: 'hint' }, `Couldn't load scores: ${error.message}`));
  }
}

async function loadSimilar(wineId, box) {
  try {
    const data = await api.similar(wineId);
    const items = (data.suggestions || []).map((suggestion) => el('div', {
      class: 'suggest-item' + (suggestion.already_owned ? ' owned' : ''),
    },
      el('div', { class: 'title' },
        [suggestion.producer, suggestion.wine_name].filter(Boolean).join(' '),
        suggestion.already_owned ? el('span', { class: 'tag', style: 'margin-left:.5rem' }, 'in your cellar') : null),
      el('div', { class: 'meta hint' },
        [(suggestion.varietals || []).join(', '), suggestion.region, suggestion.country].filter(Boolean).join(' · '),
        suggestion.typical_price_usd ? ` · ~${money(suggestion.typical_price_usd)}` : ''),
      suggestion.because ? el('div', { class: 'because' }, suggestion.because) : null));

    box.replaceChildren(el('h3', {}, 'You may also like'),
      items.length ? el('div', { class: 'suggest' }, ...items) : el('p', { class: 'hint' }, 'No suggestions returned.'));
  } catch (error) {
    box.replaceChildren(el('h3', {}, 'You may also like'), el('p', { class: 'hint' }, `Couldn't load suggestions: ${error.message}`));
  }
}

function drinkForm(bottle, refresh) {
  const quantity = el('input', { type: 'number', min: '1', max: String(bottle.quantity), value: '1' });
  const rating = el('input', { type: 'number', min: '0', max: '100', placeholder: '92' });
  const disposition = select(
    [['consumed', 'Drank it'], ['gifted', 'Gave it away'], ['sold', 'Sold it'], ['lost', 'Lost / broken']],
    'consumed');
  const note = el('textarea', { placeholder: 'Who was there, what it was with, how it showed…' });
  const save = el('button', { class: 'btn-primary', type: 'submit' }, 'Record it');

  const close = modal(`Drink ${bottle.wine.display_name}`, el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      save.disabled = true;
      try {
        await api.consumeBottle(bottle.id, {
          quantity: Number(quantity.value) || 1,
          disposition: disposition.value,
          my_rating: rating.value ? Number(rating.value) : null,
          note: note.value.trim() || null,
        });
        toast('Recorded', 'ok');
        close();
        await refresh();
      } catch (error) { toast(error.message, 'error'); save.disabled = false; }
    },
  },
    el('div', { class: 'field-grid' },
      field('How many', quantity),
      field('Disposition', disposition),
      field('Your rating /100', rating)),
    field('Note', note),
    el('div', { class: 'btn-row' }, save,
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => close() }, 'Cancel'))));
}

async function moveForm(bottle, refresh) {
  const cellars = await state.cellars();
  const options = cellars.filter((c) => c.id !== bottle.cellar_id).map((c) => [c.id, c.name]);
  if (!options.length) { toast('Create a second cellar first', 'error'); return; }

  const target = select(options, options[0][0]);
  const quantity = el('input', { type: 'number', min: '1', max: String(bottle.quantity), value: String(bottle.quantity) });
  const bin = el('input', { placeholder: 'Bin or slot in the new cellar' });
  const save = el('button', { class: 'btn-primary', type: 'submit' }, 'Move');

  const close = modal(`Move ${bottle.wine.display_name}`, el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      save.disabled = true;
      try {
        await api.moveBottle(bottle.id, {
          to_cellar_id: Number(target.value),
          quantity: Number(quantity.value) || bottle.quantity,
          bin: bin.value.trim() || null,
        });
        toast('Moved', 'ok');
        close();
        await refresh();
      } catch (error) { toast(error.message, 'error'); save.disabled = false; }
    },
  },
    el('div', { class: 'field-grid' }, field('To cellar', target), field('How many', quantity)),
    field('Bin', bin),
    el('div', { class: 'btn-row' }, save,
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => close() }, 'Cancel'))));
}

function editForm(bottle, refresh) {
  const quantity = el('input', { type: 'number', min: '0', value: String(bottle.quantity) });
  const bin = el('input', { value: bottle.bin || '' });
  const price = el('input', { type: 'number', step: '0.01', min: '0', value: bottle.purchase_price ?? '' });
  const purchased = el('input', { type: 'date', value: bottle.purchase_date || '' });
  const source = el('input', { value: bottle.purchase_source || '', placeholder: 'Merchant, auction, gift…' });
  const rating = el('input', { type: 'number', min: '0', max: '100', value: bottle.my_rating ?? '' });
  const notes = el('textarea', {}, bottle.notes || '');
  const save = el('button', { class: 'btn-primary', type: 'submit' }, 'Save');

  const close = modal('Edit bottle', el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      save.disabled = true;
      try {
        await api.updateBottle(bottle.id, {
          quantity: Number(quantity.value),
          bin: bin.value.trim() || null,
          purchase_price: price.value ? Number(price.value) : null,
          purchase_date: purchased.value || null,
          purchase_source: source.value.trim() || null,
          my_rating: rating.value ? Number(rating.value) : null,
          notes: notes.value.trim() || null,
        });
        toast('Saved', 'ok');
        close();
        await refresh();
      } catch (error) { toast(error.message, 'error'); save.disabled = false; }
    },
  },
    el('div', { class: 'field-grid' },
      field('Quantity', quantity), field('Bin', bin),
      field('Price each', price), field('Purchased', purchased),
      field('My rating /100', rating)),
    field('Bought from', source),
    field('Notes', notes),
    el('div', { class: 'btn-row' }, save,
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => close() }, 'Cancel'))));
}
