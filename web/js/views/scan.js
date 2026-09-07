// Photograph a label, get the fields filled in.
//
// The photo is downscaled in the browser before upload: phone cameras produce
// 4-12MB images and the API caps at 5MB, so a 1600px long edge at JPEG 0.85 is
// both well under the ceiling and more than the model needs to read a label.
//
// The result is never saved silently. It lands in the add-bottle form for the
// user to confirm, with per-field confidence shown for anything shaky.

import { api } from '../api.js';
import { config } from '../config.js';
import { state } from '../state.js';
import { debounce, el, empty, field, loading, money, mount, nodes, select, toast } from '../ui.js';
import { routeQuery, navigate } from '../app.js';
import { placeNames, resolveLocally } from '../reference.js';

// Offered as one-tap chips when a producer is not recognized. Chosen for how
// often they turn up in a cellar, not for prestige.
const COMMON_PLACES = [
  'Napa Valley', 'Sonoma County', 'Russian River Valley', 'Paso Robles',
  'Willamette Valley', 'Columbia Valley', 'Bordeaux', 'Burgundy', 'Champagne',
  'Chateauneuf-du-Pape', 'Chianti Classico', 'Barolo', 'Rioja', 'Douro',
  'Mosel', 'Barossa Valley', 'Marlborough', 'Mendoza', 'Stellenbosch',
];

const MAX_EDGE = 1600;
const JPEG_QUALITY = 0.85;

export async function scanView() {
  const params = routeQuery();
  const cellars = await state.cellars();

  if (!cellars.length) {
    return mount(empty('🗄️', 'Create a cellar first',
      el('p', {}, 'Bottles go into a cellar, so there needs to be one.'),
      el('a', { class: 'btn btn-primary', href: '#/cellars' }, 'Create a cellar')));
  }

  if (params.manual) return mount(...manualPage(cellars));

  const output = el('div', {});
  const preview = el('div', {});

  const fileInput = el('input', {
    type: 'file', accept: 'image/*', capture: 'environment',
    style: 'display:none',
    onChange: (event) => {
      const file = event.target.files?.[0];
      if (file) handleFile(file, preview, output, cellars);
      event.target.value = '';
    },
  });

  const drop = el('div', {
    class: 'scan-drop',
    onDragOver: (event) => { event.preventDefault(); drop.classList.add('dragging'); },
    onDragLeave: () => drop.classList.remove('dragging'),
    onDrop: (event) => {
      event.preventDefault();
      drop.classList.remove('dragging');
      const file = event.dataTransfer?.files?.[0];
      if (file) handleFile(file, preview, output, cellars);
    },
  },
    el('div', { style: 'font-size:2.4rem' }, '📷'),
    el('h2', {}, 'Scan a wine label'),
    el('p', { class: 'hint' }, 'Take a photo of the front label. Producer, vintage, varietals, region, drink window, and a value estimate come back filled in.'),
    el('div', { class: 'btn-row', style: 'justify-content:center' },
      el('button', { class: 'btn-primary', type: 'button', onClick: () => fileInput.click() }, 'Take / choose photo'),
      navigator.mediaDevices?.getUserMedia
        ? el('button', { type: 'button', onClick: () => liveCamera(preview, output, cellars) }, 'Use live camera')
        : null,
      el('a', { class: 'btn btn-ghost', href: '#/scan?manual=1' }, 'Enter by hand')),
    fileInput);

  return mount(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Scan'),
        el('p', {}, 'One photo instead of eight form fields.'))),
    config.usingDemo
      ? el('div', { class: 'banner warn' }, 'Demo mode returns a fixed sample result. Connect your API in Settings to read real labels.')
      : null,
    drop, preview, output);
}

/** Downscale and re-encode, so a 12MB phone photo becomes a ~300KB JPEG. */
function shrink(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read that file.'));
    reader.onload = () => {
      const image = new Image();
      image.onerror = () => reject(new Error('That file is not an image we can read.'));
      image.onload = () => {
        const scale = Math.min(1, MAX_EDGE / Math.max(image.width, image.height));
        const canvas = el('canvas');
        canvas.width = Math.round(image.width * scale);
        canvas.height = Math.round(image.height * scale);
        canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', JPEG_QUALITY));
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

async function handleFile(file, previewBox, output, cellars) {
  if (!file.type.startsWith('image/')) { toast('That is not an image', 'error'); return; }

  let dataUrl;
  try {
    dataUrl = await shrink(file);
  } catch (error) { toast(error.message, 'error'); return; }

  previewBox.replaceChildren(el('img', { class: 'scan-preview', src: dataUrl, alt: 'The label you photographed' }));
  await identify(dataUrl, output, cellars);
}

async function identify(dataUrl, output, cellars) {
  output.replaceChildren(el('div', { class: 'card' }, loading('Reading the label…')));
  try {
    const result = await api.identifyLabel(dataUrl, 'image/jpeg');
    if (!result.readable) {
      output.replaceChildren(el('div', { class: 'banner warn' },
        result.notes || 'That photo was not readable. Try again with the front label filling the frame, in even light.'));
      return;
    }
    output.replaceChildren(...resultPanel(result, cellars, dataUrl));
    output.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    output.replaceChildren(el('div', { class: 'banner error' }, error.message));
  }
}

function resultPanel(result, cellars, dataUrl) {
  const confidence = result.confidence ?? 0;
  const level = confidence >= 0.75 ? '' : confidence >= 0.45 ? 'low' : 'vlow';
  const shaky = Object.entries(result.field_confidence || {})
    .filter(([, value]) => Number(value) < 0.6)
    .map(([key]) => key);

  return [
    el('section', { class: 'card' },
      el('h2', {}, 'What we read'),
      el('div', { class: `confidence ${level}` }, el('i', { style: `width:${Math.round(confidence * 100)}%` })),
      el('p', { class: 'hint', style: 'margin-top:.4rem' },
        `${Math.round(confidence * 100)}% confident overall.`
        + (shaky.length ? ` Double-check: ${shaky.join(', ')}.` : '')),
      result.notes ? el('p', { class: 'hint' }, result.notes) : null,
      result.estimated_value
        ? el('p', { class: 'hint' },
            `Estimated value ${money(result.estimated_value.low, result.estimated_value.currency)}–${money(result.estimated_value.high, result.estimated_value.currency)} per bottle. `,
            el('span', { class: 'tag estimate' }, 'estimate'))
        : null),
    ...manualPage(cellars, result.wine, result.estimated_value, dataUrl),
  ];
}

/** The add-bottle form. Shared by the scan flow (pre-filled) and manual entry. */
function manualPage(cellars, prefill = {}, estimatedValue = null, labelImage = null) {
  const producer = el('input', { value: prefill.producer || '', required: true, placeholder: 'Château Margaux' });
  const wineName = el('input', { value: prefill.wine_name || '', placeholder: 'Grand Vin' });
  const vintage = el('input', { type: 'number', min: '1800', max: '2100', value: prefill.vintage ?? '', placeholder: 'blank = NV' });
  const varietals = el('input', { value: (prefill.varietals || []).join(', '), placeholder: 'Cabernet Sauvignon, Merlot' });
  const wineType = select(
    [['', '—'], ['red', 'Red'], ['white', 'White'], ['rose', 'Rosé'], ['sparkling', 'Sparkling'],
     ['dessert', 'Dessert'], ['fortified', 'Fortified'], ['other', 'Other']],
    prefill.wine_type || '');
  // The place fields autocomplete from the reference. Naming a region is the
  // single most useful thing a user can add when a producer is unrecognized —
  // it is what turns "no match" into a filled country, grape set and window.
  const country = el('input', { value: prefill.country || '', placeholder: 'France', list: 'wv-countries', autocomplete: 'off' });
  const region = el('input', { value: prefill.region || '', placeholder: 'Bordeaux', list: 'wv-regions', autocomplete: 'off' });
  const appellation = el('input', { value: prefill.appellation || '', placeholder: 'Margaux', list: 'wv-appellations', autocomplete: 'off' });
  const placeLists = el('div', { hidden: true });

  placeNames().then(({ appellations, regions, countries }) => {
    const list = (id, values) => el('datalist', { id }, ...values.map((v) => el('option', { value: v })));
    placeLists.replaceChildren(
      list('wv-appellations', appellations),
      list('wv-regions', regions),
      list('wv-countries', countries));
  }).catch(() => { /* autocomplete is a convenience; the fields work without it */ });
  const sizeMl = el('input', { type: 'number', min: '50', max: '30000', value: prefill.bottle_size_ml || 750 });
  const abv = el('input', { type: 'number', step: '0.1', min: '0', max: '100', value: prefill.abv ?? '' });
  const drinkFrom = el('input', { type: 'number', min: '1800', max: '2200', value: prefill.drink_from ?? '' });
  const drinkTo = el('input', { type: 'number', min: '1800', max: '2200', value: prefill.drink_to ?? '' });

  // ---- autofill -------------------------------------------------------
  // Producer and vintage imply most of the rest, so once both are present we
  // ask the backend and fill in the fields the user has left empty. Anything
  // they typed themselves is never overwritten.

  const AUTOFILLABLE = [
    ['wine_name', wineName], ['varietals', varietals], ['wine_type', wineType],
    ['country', country], ['region', region], ['appellation', appellation],
    ['abv', abv], ['drink_from', drinkFrom], ['drink_to', drinkTo],
  ];

  const status = el('div', { class: 'lookup-status', hidden: true });
  const bottlingRow = el('div', { class: 'lookup-bottlings', hidden: true });
  const valueHint = el('div', { class: 'hint value-hint', hidden: true });

  // Fields the user has typed in are off-limits; ones we filled stay fair game
  // so a later, sharper lookup can correct them.
  const userEdited = new Set();
  for (const [key, input] of AUTOFILLABLE) {
    input.addEventListener('input', () => {
      if (input.dataset.autofilled === '1') {
        delete input.dataset.autofilled;
        input.classList.remove('autofilled');
      }
      if (input.value.trim()) userEdited.add(key); else userEdited.delete(key);
    });
  }

  let lastQuery = '';
  let inFlight = 0;

  /** Offer a market estimate beside the price field — never write it in.
   *  "Price each" is what you paid, and the value tracker's gain is computed
   *  against exactly that number. */
  function showValueHint(estimate) {
    if (!estimate?.mid) return;
    valueHint.hidden = false;
    valueHint.replaceChildren(
      `Market estimate ${money(estimate.low ?? estimate.mid, estimate.currency)}–${money(estimate.high ?? estimate.mid, estimate.currency)} per bottle. `,
      el('button', {
        type: 'button', class: 'linkish',
        onClick: () => { price.value = estimate.mid; },
      }, `Use ${money(estimate.mid, estimate.currency)}`),
      ' — only if that is what you actually paid.');
  }

  const setField = (key, input, value) => {
    if (userEdited.has(key) || value === null || value === undefined || value === '') return false;
    input.value = value;
    input.dataset.autofilled = '1';
    input.classList.add('autofilled');
    return true;
  };

  async function runLookup({ manual = false } = {}) {
    const name = producer.value.trim();
    const year = vintage.value.trim();
    const cuvee = wineName.value.trim();
    if (name.length < 3) {
      if (manual) toast('Enter a producer first', 'error');
      return;
    }

    const signature = [name, year, cuvee, region.value.trim(), appellation.value.trim()].join('|');
    if (!manual && signature === lastQuery) return;
    lastQuery = signature;

    const ticket = ++inFlight;
    status.hidden = false;
    status.replaceChildren(el('span', { class: 'spinner' }), ` Looking up ${name}${year ? ' ' + year : ''}…`);
    // Drop the previous producer's suggestions the moment a new lookup starts —
    // otherwise they stay clickable and a stale cuvée can be picked for a wine
    // it does not belong to.
    bottlingRow.hidden = true;
    bottlingRow.replaceChildren();
    valueHint.hidden = true;
    valueHint.replaceChildren();

    // Everything the user has typed goes in — the more context, the better the
    // match, and a region alone is enough to fill a country and grape set.
    const params = {
      producer: name,
      vintage: year ? Number(year) : null,
      wine_name: cuvee || null,
      // One grape, as a hint for the search. Only ever the user's own — sending
      // back the first entry of a list autofill wrote would ask the server to
      // treat a blend's lead grape as a stated fact.
      varietal: userEdited.has('varietals') ? varietals.value.split(',')[0].trim() || null : null,
      country: country.value.trim() || null,
      region: region.value.trim() || null,
      appellation: appellation.value.trim() || null,
    };

    let result;
    try {
      result = await api.lookupWine(params);
    } catch (error) {
      // The backend is unreachable — resolve from the built-in reference rather
      // than leaving the user with nothing.
      if (ticket !== inFlight) return;
      result = await offlineResult(params, error.message);
    }
    if (ticket !== inFlight) return;

    if (!result.found) {
      status.replaceChildren(...nodes(
        el('span', { class: 'lookup-warn' }, `No match for “${name}”.`),
        // The backend explains itself — surface that rather than a bare "no match".
        result.notes ? el('div', { class: 'hint' }, result.notes) : null,
        el('div', { class: 'hint' },
          'Everything still saves normally — fill in what you know.'),
        // A curated reference always has a long tail. Naming the place is the
        // way out of it, so make that one tap rather than one more thing to type.
        (!region.value.trim() && !appellation.value.trim())
          ? el('div', { style: 'margin-top:.6rem' },
              el('div', { class: 'hint' }, 'Where is it from? One tap fills the country, grapes and drinking window:'),
              el('div', { class: 'chip-row', style: 'margin-top:.35rem' },
                ...COMMON_PLACES.map((place) => el('button', {
                  class: 'chip', type: 'button',
                  onClick: () => {
                    appellation.value = place;
                    appellation.dataset.autofilled = '1';
                    appellation.classList.add('autofilled');
                    lastQuery = '';
                    runLookup({ manual: true });
                  },
                }, place)),
                el('button', {
                  class: 'chip', type: 'button',
                  onClick: () => {
                    region.scrollIntoView({ block: 'center', behavior: 'smooth' });
                    region.focus();
                  },
                }, 'Somewhere else…')))
          : null));
      bottlingRow.hidden = true;
      return;
    }

    const wine = result.wine || {};
    let filled = 0;
    for (const [key, input] of AUTOFILLABLE) {
      const value = key === 'varietals' ? (wine.varietals || []).join(', ') : wine[key];
      if (setField(key, input, value)) filled += 1;
    }
    if (!userEdited.has('producer') && wine.producer && wine.producer !== name) {
      producer.value = wine.producer;   // spelling correction
    }
    if (!sizeMl.value || sizeMl.value === '750') {
      sizeMl.value = wine.bottle_size_ml || 750;
    }

    showValueHint(result.estimated_value);

    const shaky = Object.entries(result.field_confidence || {})
      .filter(([, value]) => Number(value) < 0.6).map(([key]) => key.replace(/_/g, ' '));

    // Say plainly when the wine was placed by its region rather than recognized
    // by name — those fields are a regional norm, not a fact about this bottle.
    // A partial or weak producer match counts as "not recognized": those are
    // precisely the results that most need the caveat, and gating on the mere
    // presence of a match hid it from them.
    const recognized = result.reference_match === 'exact' || result.reference_match === 'strong';
    const placedByRegion = !recognized && result.reference_place;

    status.replaceChildren(...nodes(
      el('span', { class: filled ? 'lookup-ok' : 'lookup-warn' },
        filled ? `✓ Filled ${filled} field${filled === 1 ? '' : 's'}.` : 'Nothing left to fill.'),
      placedByRegion
        ? el('div', { class: 'hint' },
            `Placed from ${result.reference_place.name}, not from the producer — `
            + 'these are typical for the region, so check them against the bottle.')
        : null,
      result.vintage_note ? el('div', { class: 'hint' }, result.vintage_note) : null,
      shaky.length ? el('div', { class: 'hint' }, `Worth checking: ${shaky.join(', ')}.`) : null,
      result.model_error
        ? el('div', { class: 'hint' }, `Lookup service unreachable, so this is the offline reference only (${result.model_error}).`)
        : result.notes ? el('div', { class: 'hint' }, result.notes) : null,
      el('div', { class: 'hint' }, 'Autofilled fields are marked — edit any of them freely.')));

    // Offer the producer's range so the user can name the bottling.
    const bottlings = (result.bottlings || []).filter((b) => b.wine_name);
    if (bottlings.length && !wineName.value.trim()) {
      bottlingRow.hidden = false;
      bottlingRow.replaceChildren(
        el('div', { class: 'hint' }, 'Which bottling? Picking one sharpens the rest.'),
        el('div', { class: 'chip-row' }, ...bottlings.map((bottling) => el('button', {
          class: 'chip', type: 'button', title: bottling.note || '',
          onClick: () => {
            wineName.value = bottling.wine_name;
            wineName.dataset.autofilled = '1';
            wineName.classList.add('autofilled');
            bottlingRow.hidden = true;
            runLookup({ manual: true });
          },
        }, bottling.wine_name))));
    } else {
      bottlingRow.hidden = true;
    }
  }

  /** Resolve from the built-in reference when the API cannot be reached. */
  async function offlineResult(query, reason) {
    const local = await resolveLocally(query);
    const wine = { ...local.wine, bottle_size_ml: 750 };
    const confident = local.producer_match === 'exact' || local.producer_match === 'strong';
    wine.producer = (confident && local.producer_name) || query.producer;
    const found = Boolean(wine.country || wine.region);
    return {
      found, wine, sources: local.sources, bottlings: [], estimated_value: null,
      confidence: null,
      field_confidence: Object.fromEntries((local.typical || []).map((f) => [f, 0.55])),
      vintage_note: null,
      notes: found ? null : `Couldn't reach the lookup service (${reason}), and the producer is not in the built-in reference.`,
      reference_match: local.producer_match, reference_place: local.place,
      model_error: found ? reason : null, needs_review: true,
    };
  }

  const scheduleLookup = debounce(() => runLookup(), 700);
  producer.addEventListener('input', scheduleLookup);
  vintage.addEventListener('input', scheduleLookup);
  // Typing a region is new evidence, so re-ask — that is how an unrecognized
  // producer still gets a country, a grape set and a drinking window.
  for (const input of [region, appellation]) {
    input.addEventListener('change', () => { lastQuery = ''; runLookup(); });
  }
  producer.addEventListener('input', () => { if (producer.value.trim()) userEdited.add('producer'); });

  const lookupButton = el('button', {
    type: 'button', class: 'btn-sm',
    onClick: () => runLookup({ manual: true, refresh: true }),
  }, '✨ Autofill from producer + year');

  const cellarSelect = select(cellars.map((c) => [c.id, c.name]),
    cellars.find((c) => c.id === config.activeCellarId)?.id ?? cellars[0].id);
  const quantity = el('input', { type: 'number', min: '1', value: '1' });
  const bin = el('input', { placeholder: 'A-04' });
  // Purchase price is what you PAID. Pre-filling it with a market estimate
  // would quietly corrupt the cost basis, and the value tracker's gain is
  // computed against exactly that. The estimate is offered beside the field
  // instead, one click away.
  const price = el('input', {
    type: 'number', step: '0.01', min: '0',
    placeholder: 'What you paid per bottle',
  });
  const purchased = el('input', { type: 'date', value: new Date().toISOString().slice(0, 10) });
  const source = el('input', { placeholder: 'Merchant, auction, gift…' });
  const notes = el('textarea', { placeholder: 'Anything worth remembering.' });

  const save = el('button', { class: 'btn-primary', type: 'submit' }, 'Add to cellar');

  showValueHint(estimatedValue);

  // A label rarely states region, ABV or a drinking window; a lookup on what it
  // did show fills those in without a second round of typing.
  if (prefill.producer) setTimeout(() => runLookup(), 100);

  const form = el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      if (!producer.value.trim()) { toast('A producer is required', 'error'); producer.focus(); return; }
      save.disabled = true;
      try {
        const created = await api.addBottle({
          cellar_id: Number(cellarSelect.value),
          quantity: Number(quantity.value) || 1,
          bin: bin.value.trim() || null,
          purchase_price: price.value ? Number(price.value) : null,
          purchase_date: purchased.value || null,
          purchase_source: source.value.trim() || null,
          notes: notes.value.trim() || null,
          wine: {
            producer: producer.value.trim(),
            wine_name: wineName.value.trim() || null,
            vintage: vintage.value ? Number(vintage.value) : null,
            varietals: varietals.value.split(',').map((v) => v.trim()).filter(Boolean),
            wine_type: wineType.value || null,
            country: country.value.trim() || null,
            region: region.value.trim() || null,
            appellation: appellation.value.trim() || null,
            bottle_size_ml: Number(sizeMl.value) || 750,
            abv: abv.value ? Number(abv.value) : null,
            drink_from: drinkFrom.value ? Number(drinkFrom.value) : null,
            drink_to: drinkTo.value ? Number(drinkTo.value) : null,
            label_image_url: labelImage && labelImage.length < 200 ? labelImage : null,
          },
        });
        config.activeCellarId = Number(cellarSelect.value);
        state.invalidate();
        toast(`Added ${created.wine?.display_name || producer.value.trim()}`, 'ok');
        navigate('#/inventory', {});
      } catch (error) {
        toast(error.message, 'error');
        save.disabled = false;
      }
    },
  },
    el('h2', {}, prefill.producer ? 'Confirm and save' : 'Add a bottle'),
    el('p', { class: 'hint' }, prefill.producer
      ? 'Read off the label — correct anything that looks wrong before saving.'
      : 'Type the producer and the vintage; the rest fills itself in. Everything except the producer is optional.'),
    el('div', { class: 'field-grid' },
      field('Producer *', producer),
      field('Cuvée / name', wineName),
      field('Vintage', vintage),
      field('Type', wineType)),
    el('div', { class: 'btn-row', style: 'margin:-.2rem 0 .6rem' }, lookupButton),
    status,
    bottlingRow,
    field('Varietals', varietals, 'Comma-separated.'),
    el('div', { class: 'field-grid' },
      field('Country', country), field('Region', region), field('Appellation', appellation)),
    placeLists,
    el('div', { class: 'field-grid' },
      field('Size (ml)', sizeMl), field('ABV %', abv),
      field('Drink from', drinkFrom), field('Drink to', drinkTo)),
    el('hr', { style: 'border:none;border-top:1px solid var(--line-soft);margin:1rem 0' }),
    el('div', { class: 'field-grid' },
      field('Cellar', cellarSelect), field('Quantity', quantity), field('Bin', bin)),
    el('div', { class: 'field-grid' },
      field('Price each', price), field('Purchased', purchased)),
    valueHint,
    field('Bought from', source),
    field('Notes', notes),
    el('div', { class: 'btn-row' }, save,
      el('a', { class: 'btn btn-ghost', href: '#/inventory' }, 'Cancel')));

  return [el('section', { class: 'card', style: 'margin-top:.8rem' }, form)];
}

/** Live viewfinder for desktops, where the file input won't open a camera. */
async function liveCamera(previewBox, output, cellars) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
  } catch {
    toast('Could not open the camera. Use "Take / choose photo" instead.', 'error');
    return;
  }

  const video = el('video', { id: 'scan-video', autoplay: true, playsinline: true, muted: true });
  video.srcObject = stream;

  const stop = () => { stream.getTracks().forEach((track) => track.stop()); previewBox.replaceChildren(); };

  const capture = el('button', {
    class: 'btn-primary', type: 'button',
    onClick: async () => {
      const canvas = el('canvas');
      const scale = Math.min(1, MAX_EDGE / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY);
      stop();
      previewBox.replaceChildren(el('img', { class: 'scan-preview', src: dataUrl, alt: 'The label you captured' }));
      await identify(dataUrl, output, cellars);
    },
  }, 'Capture');

  previewBox.replaceChildren(el('div', { class: 'card' }, video,
    el('div', { class: 'btn-row', style: 'margin-top:.6rem' }, capture,
      el('button', { class: 'btn-ghost', type: 'button', onClick: stop }, 'Cancel'))));
}
