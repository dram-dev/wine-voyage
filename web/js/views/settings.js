// Where the app is pointed, and who it thinks you are.

import { api, ApiError } from '../api.js';
import { config } from '../config.js';
import { resetDemo } from '../demo.js';
import { state } from '../state.js';
import { el, field, mount, toast } from '../ui.js';
import { refreshConnection, refreshCellarSwitcher } from '../app.js';

// The one failure that looks like a broken server but is not: an HTTPS page
// cannot call a plain http:// API. Chrome and Firefox make an exception for
// localhost; Safari does not, which is exactly the case on an iPhone.
function mixedContentNote(base) {
  if (location.protocol !== 'https:') return null;
  let url;
  try { url = new URL(base); } catch { return null; }
  if (url.protocol !== 'http:') return null;
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  return local
    ? 'This page is HTTPS and the API is plain http://localhost. Chrome and Firefox allow that; Safari blocks it.'
    : 'This page is HTTPS, so the browser blocks calls to a plain http:// address. Give the server an HTTPS name — `tailscale serve` does it in one command — or open this app from your own machine over http.';
}

export function settingsView() {
  const apiInput = el('input', {
    value: config.apiBase, placeholder: 'https://mac-mini.tailnet.ts.net',
    inputmode: 'url', spellcheck: 'false',
  });
  const accountInput = el('input', { value: config.accountId, spellcheck: 'false' });
  const demoToggle = el('input', { type: 'checkbox', style: 'width:auto', checked: config.demoMode });
  const status = el('div', { class: 'hint' });

  const say = (text, kind = '') => {
    status.textContent = text;
    status.style.color = kind === 'ok' ? 'var(--ok, #6cc070)' : kind === 'bad' ? 'var(--accent)' : '';
  };

  const testButton = el('button', {
    type: 'button',
    onClick: async () => {
      const previous = config.apiBase;
      config.apiBase = apiInput.value;
      apiInput.value = config.apiBase; // show the normalized form back
      const wasDemo = config.demoMode;
      config.demoMode = false;
      say('Checking…');
      try {
        await api.health();
        say('✅ Reached the API. Save to start using it.', 'ok');
      } catch (error) {
        const note = mixedContentNote(config.apiBase);
        const detail = error instanceof ApiError ? error.message : String(error);
        say(note ? `❌ ${note}` : `❌ ${detail}`, 'bad');
        config.apiBase = previous;
      } finally {
        config.demoMode = wasDemo;
      }
    },
  }, 'Test connection');

  const saveButton = el('button', { class: 'btn-primary', type: 'submit' }, 'Save settings');

  const form = el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      config.apiBase = apiInput.value;
      apiInput.value = config.apiBase;
      config.accountId = accountInput.value.trim() || config.accountId;
      config.demoMode = demoToggle.checked;
      config.activeCellarId = null;
      state.invalidate();
      toast('Settings saved', 'ok');
      await refreshConnection();
      await refreshCellarSwitcher();

      // Landing on an empty account with nowhere to put a bottle is a dead end.
      if (!config.usingDemo) {
        try {
          const cellars = await state.cellars({ force: true });
          if (!cellars.length) {
            const created = await api.createCellar({ name: 'My cellar', is_default: true });
            config.activeCellarId = created.id;
            state.invalidate();
            await refreshCellarSwitcher();
            toast('Created your first cellar', 'ok');
          }
        } catch { /* the connection banner already reports an unreachable API */ }
      }
    },
  },
    field('API base URL', apiInput,
      'The address of your Wine Voyage server, without a path — the app adds /api itself. Leave blank to browse the sample cellar.'),
    field('Account ID', accountInput,
      'Your cellars are keyed to this id. Copy it to another device to see the same cellars there. Anyone with the id can read and change your cellar, so treat it like a password.'),
    el('label', { class: 'field', style: 'display:flex;gap:.5rem;align-items:center' },
      demoToggle,
      el('span', { style: 'margin:0;text-transform:none;letter-spacing:0;font-size:.9rem' },
        'Always use the sample cellar, even with an API configured')),
    el('div', { class: 'btn-row' }, saveButton, testButton),
    status);

  const shareUrl = config.apiBase
    ? `${location.origin}${location.pathname}?api=${encodeURIComponent(config.apiBase)}&account=${encodeURIComponent(config.accountId)}`
    : null;

  return mount(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Settings'),
        el('p', {}, 'This page is static; your cellar data lives on your own server.'))),
    el('section', { class: 'card' }, form),

    shareUrl
      ? el('section', { class: 'card' },
          el('h3', {}, 'Set up another device'),
          el('p', { class: 'hint' }, 'Open this link on your phone to point it at the same server and account in one step. It contains your account id — share it only with people you want in your cellar.'),
          el('input', { value: shareUrl, readonly: true, onClick: (event) => event.target.select() }))
      : null,

    el('section', { class: 'card' },
      el('h3', {}, 'Sample data'),
      el('p', { class: 'hint' },
        config.usingDemo
          ? 'You are browsing the sample cellar. It is generated in this browser tab and never written anywhere — no database, not even local storage. There is nothing to delete: the moment you save a working API base URL above, it is gone and you are looking at your own cellar.'
          : 'You are on your own server; the sample cellar is not in play. It only appears when no API base URL is set, or when the box above is ticked.'),
      config.usingDemo
        ? el('button', {
            type: 'button',
            onClick: () => { resetDemo(); state.invalidate(); toast('Sample cellar reset', 'ok'); },
          }, 'Reset sample cellar')
        : null),

    el('section', { class: 'card' },
      el('h3', {}, 'How this fits together'),
      el('p', { class: 'hint' },
        'The site is served as static files from GitHub Pages, so it can be opened from any device with no install. It talks to the FastAPI server you run yourself — the one holding your Postgres database. Nothing about your cellar passes through GitHub.'),
      el('p', { class: 'hint' },
        'Because this page is HTTPS, browsers block calls to a plain http:// API — on an iPhone, always. Tailscale issues a real certificate for your machine, which fixes it in one command:'),
      el('pre', { style: 'overflow-x:auto' },
        el('code', {}, 'tailscale serve --bg --https=443 http://127.0.0.1:8420')),
      el('p', { class: 'hint' },
        'Then the API base URL above is https://your-machine.your-tailnet.ts.net — no port, no path.')),
  );
}
