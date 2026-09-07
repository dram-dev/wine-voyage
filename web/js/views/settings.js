// Where the app is pointed, and who it thinks you are.

import { api, ApiError } from '../api.js';
import { config } from '../config.js';
import { resetDemo } from '../demo.js';
import { state } from '../state.js';
import { el, field, mount, toast } from '../ui.js';
import { refreshConnection, refreshCellarSwitcher } from '../app.js';

export function settingsView() {
  const apiInput = el('input', {
    value: config.apiBase, placeholder: 'http://mac-mini.tailnet.ts.net:8420',
    inputmode: 'url', spellcheck: 'false',
  });
  const accountInput = el('input', { value: config.accountId, spellcheck: 'false' });
  const demoToggle = el('input', { type: 'checkbox', style: 'width:auto', checked: config.demoMode });
  const status = el('div', { class: 'hint' });

  const testButton = el('button', {
    type: 'button',
    onClick: async () => {
      const previous = config.apiBase;
      config.apiBase = apiInput.value;
      const wasDemo = config.demoMode;
      config.demoMode = false;
      status.textContent = 'Checking…';
      try {
        await api.health();
        status.textContent = '✅ Reached the API.';
      } catch (error) {
        status.textContent = `❌ ${error instanceof ApiError ? error.message : error}`;
        config.apiBase = previous;
      } finally {
        config.demoMode = wasDemo;
      }
    },
  }, 'Test connection');

  const saveButton = el('button', {
    class: 'btn-primary', type: 'submit',
  }, 'Save settings');

  const form = el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      config.apiBase = apiInput.value;
      config.accountId = accountInput.value.trim() || config.accountId;
      config.demoMode = demoToggle.checked;
      config.activeCellarId = null;
      state.invalidate();
      toast('Settings saved', 'ok');
      await refreshConnection();
      await refreshCellarSwitcher();
    },
  },
    field('API base URL', apiInput,
      'Where your Wine Voyage server runs — a Tailscale hostname, a LAN address, or http://localhost:8420. Leave blank to browse the sample cellar.'),
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
      el('h3', {}, 'How this fits together'),
      el('p', { class: 'hint' },
        'The site is served as static files from GitHub Pages, so it can be opened from any device with no install. It talks to the FastAPI server you run yourself — the one holding your Postgres database. Nothing about your cellar passes through GitHub.'),
      el('p', { class: 'hint' },
        'Because the page is served over HTTPS, browsers will block calls to a plain http:// API on some setups. A Tailscale HTTPS hostname, a reverse proxy with a certificate, or running this page locally all avoid that.')),

    el('section', { class: 'card' },
      el('h3', {}, 'Sample data'),
      el('p', { class: 'hint' }, 'Reset the demo cellar back to its starting bottles.'),
      el('button', {
        type: 'button',
        onClick: () => { resetDemo(); state.invalidate(); toast('Sample cellar reset', 'ok'); },
      }, 'Reset sample cellar')),
  );
}
