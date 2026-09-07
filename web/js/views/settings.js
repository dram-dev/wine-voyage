// Connecting the app to your own server.
//
// This page used to open with two pieces of jargon — an "API base URL" and a
// raw account UUID — beside two buttons that had to be pressed in the right
// order. There is really only ever one question here (is this app showing you
// your cellar, or the sample one?), so the page asks that and nothing else.
// Everything a first-time user should not touch is behind Advanced.

import { api, ApiError } from '../api.js';
import { config } from '../config.js';
import { resetDemo } from '../demo.js';
import { state } from '../state.js';
import { el, field, mount, nodes, toast } from '../ui.js';
import { refreshConnection, refreshCellarSwitcher } from '../app.js';

const SETUP_COMMANDS = `python -m scripts.bootstrap_db
./scripts/install_launchd.sh
tailscale serve --bg --https=443 http://127.0.0.1:8420`;

// The one failure that looks like a broken server but is not: an HTTPS page
// cannot call a plain http:// address. Chrome and Firefox make an exception for
// localhost; Safari does not, which is exactly the case on an iPhone.
function mixedContentNote(base) {
  if (location.protocol !== 'https:') return null;
  let url;
  try { url = new URL(base); } catch { return null; }
  if (url.protocol !== 'http:') return null;
  return ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
    ? 'This page is secure (https) and that address is not. Chrome and Firefox allow it for localhost; Safari never does.'
    : 'That address starts with http://, and a secure page cannot call an insecure one. Your browser blocked it before it left. Give the server an https name — one tailscale serve command does it — and try again.';
}

// `new URL()` is not a validity check. Browsers accept "https://my mac mini"
// and percent-encode the spaces into the hostname, which then fails as a DNS
// lookup a second later — a confusing way to be told you typed a sentence.
function looksLikeAnAddress(value) {
  let url;
  try { url = new URL(value); } catch { return false; }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return false;
  // A dotless host is legitimate — Tailscale MagicDNS and LAN names both do it
  // — so the test is only that this could be a host at all, not that it is one.
  const host = url.hostname;
  return Boolean(host) && !/[^a-z0-9.:[\]-]/i.test(host);
}

export function settingsView() {
  return mount(...nodes(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Settings'))),
    config.usingDemo ? connectCard() : connectedCard(),
    config.usingDemo ? null : shareCard(),
    advancedCard(),
  ));
}

/** Not connected: one field, one button, one outcome. */
function connectCard() {
  const input = el('input', {
    value: config.apiBase,
    placeholder: 'https://mac-mini.tailnet.ts.net',
    inputmode: 'url', spellcheck: 'false', autocapitalize: 'off',
  });
  const status = el('div', { class: 'hint', style: 'margin-top:.5rem' });

  const say = (text, kind = '') => {
    status.replaceChildren(text);
    status.style.color = kind === 'bad' ? 'var(--amber)' : '';
  };

  const connect = el('button', { class: 'btn-primary', type: 'submit' }, 'Connect');

  // Test and save are one action. Separating them only ever asked the user to
  // decide something they had no way to decide.
  const form = el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      const typed = input.value.trim();
      if (!typed) return say('Enter the address of your server first.', 'bad');
      if (!looksLikeAnAddress(typed) && !looksLikeAnAddress(`https://${typed}`)) {
        return say(`“${typed}” does not look like an address. It should look like https://mac-mini.tailnet.ts.net`, 'bad');
      }

      const previous = { api: config.apiBase, demo: config.demoMode };
      config.apiBase = looksLikeAnAddress(typed) ? typed : `https://${typed}`;
      config.demoMode = false;
      input.value = config.apiBase;
      connect.disabled = true;
      say('Connecting…');

      try {
        await api.health();
      } catch (error) {
        config.apiBase = previous.api;
        config.demoMode = previous.demo;
        connect.disabled = false;
        const note = mixedContentNote(input.value.trim());
        return say(note || (error instanceof ApiError ? error.message : String(error)), 'bad');
      }

      // Reachable. Make sure there is somewhere to put a bottle before handing
      // the user back to an app whose Scan page would otherwise dead-end.
      config.activeCellarId = null;
      state.invalidate();
      try {
        const cellars = await state.cellars({ force: true });
        if (!cellars.length) {
          const created = await api.createCellar({ name: 'My cellar', is_default: true });
          config.activeCellarId = created.id;
          state.invalidate();
        }
      } catch { /* the connection badge reports anything still wrong */ }

      toast('Connected — this is your cellar now', 'ok');
      await refreshConnection();
      await refreshCellarSwitcher();
      location.hash = '#/dashboard';
    },
  },
    field('Your server address', input,
      el('span', {}, 'The machine running Wine Voyage. Paste the https name that ',
        el('code', {}, 'tailscale serve status'), ' prints.')),
    el('div', { class: 'btn-row' }, connect),
    status);

  return el('section', { class: 'card' },
    el('h2', { style: 'margin-top:0' }, 'Connect your cellar'),
    el('p', { class: 'hint', style: 'margin-bottom:1rem' },
      'You are looking at sample wines. Nothing you do to them is saved. '
      + 'Point this app at your own server and you will see your own bottles instead.'),
    form,
    el('details', { style: 'margin-top:1rem' },
      el('summary', { style: 'cursor:pointer;color:var(--ink-dim)' }, 'No server running yet?'),
      el('p', { class: 'hint', style: 'margin-top:.6rem' },
        'On the machine that will hold your cellar, from a checkout of this repository:'),
      el('pre', { style: 'overflow-x:auto' }, el('code', {}, SETUP_COMMANDS)),
      el('p', { class: 'hint' },
        'The last line is what gives the server an https name, which is what lets this page — '
        + 'and your phone — talk to it at all. The README has the longer version.')));
}

/** Connected: say so, and get out of the way. */
function connectedCard() {
  return el('section', { class: 'card' },
    el('h2', { style: 'margin-top:0' }, 'Your cellar'),
    el('p', {},
      el('span', { class: 'conn live', style: 'display:inline-flex' }, el('span', { class: 'dot' })),
      ' Connected to ', el('strong', {}, config.apiBase)),
    el('p', { class: 'hint' }, 'Bottles you add are saved to your own database. Nothing passes through GitHub.'),
    el('div', { class: 'btn-row' },
      el('button', {
        type: 'button',
        onClick: async () => {
          config.apiBase = '';
          config.activeCellarId = null;
          state.invalidate();
          await refreshConnection();
          await refreshCellarSwitcher();
          toast('Disconnected — showing sample wines');
          location.hash = '#/settings';
        },
      }, 'Change server')));
}

function shareCard() {
  const url = `${location.origin}${location.pathname}`
    + `?api=${encodeURIComponent(config.apiBase)}&account=${encodeURIComponent(config.accountId)}`;
  return el('section', { class: 'card' },
    el('h3', {}, 'Open this on your phone'),
    el('p', { class: 'hint' },
      'This link carries the server address and your account, so the phone is set up in one tap. '
      + 'Anyone you send it to can read and change your cellar.'),
    el('input', { value: url, readonly: true, onClick: (event) => event.target.select() }),
    el('div', { class: 'btn-row', style: 'margin-top:.5rem' },
      el('button', {
        type: 'button',
        onClick: async () => {
          try {
            await navigator.clipboard.writeText(url);
            toast('Link copied', 'ok');
          } catch {
            toast('Select the link and copy it');
          }
        },
      }, 'Copy link')));
}

/** Everything that is real but that nobody should have to meet on day one. */
function advancedCard() {
  const accountInput = el('input', { value: config.accountId, spellcheck: 'false' });
  const demoToggle = el('input', { type: 'checkbox', style: 'width:auto', checked: config.demoMode });

  return el('section', { class: 'card' },
    el('details', {},
      el('summary', { style: 'cursor:pointer;color:var(--ink-dim)' }, 'Advanced'),
      el('div', { style: 'margin-top:1rem' },
        field('Account id', accountInput,
          'Your cellars are filed under this. Changing it shows a different cellar; '
          + 'copying it to another device shows the same one. Treat it like a password.'),
        el('label', { class: 'field', style: 'display:flex;gap:.5rem;align-items:center' },
          demoToggle,
          el('span', { style: 'margin:0;text-transform:none;letter-spacing:0;font-size:.9rem' },
            'Always show sample wines, even when connected')),
        el('div', { class: 'btn-row' },
          el('button', {
            type: 'button',
            onClick: async () => {
              config.accountId = accountInput.value.trim() || config.accountId;
              config.demoMode = demoToggle.checked;
              config.activeCellarId = null;
              state.invalidate();
              toast('Saved', 'ok');
              await refreshConnection();
              await refreshCellarSwitcher();
              location.hash = '#/settings';
            },
          }, 'Save'),
          config.usingDemo
            ? el('button', {
                type: 'button',
                onClick: () => { resetDemo(); state.invalidate(); toast('Sample wines reset', 'ok'); },
              }, 'Reset sample wines')
            : null),
        el('h3', {}, 'How this fits together'),
        el('p', { class: 'hint' },
          'The site is static files on GitHub Pages, so it opens on any device with no install. '
          + 'It talks to the server you run, which holds your Postgres database. '
          + 'Your cellar never passes through GitHub.'),
        el('p', { class: 'hint' },
          'Because this page is served over https, browsers refuse to let it call a plain http:// '
          + 'address — Safari always, so an iPhone always. That is why the server needs an https '
          + 'name, and why ', el('code', {}, 'tailscale serve'), ' is in the setup.'))));
}
