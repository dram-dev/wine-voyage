import { api } from '../api.js';
import { config } from '../config.js';
import { state } from '../state.js';
import { confirmAction, count, el, field, loading, modal, money, mount, plural, toast } from '../ui.js';
import { refreshCellarSwitcher } from '../app.js';

export async function cellarsView() {
  mount(loading('Loading cellars…'));
  const cellars = await state.cellars({ force: true });

  const list = cellars.length
    ? el('div', { class: 'bottle-list' }, ...cellars.map(cellarCard))
    : el('div', { class: 'empty' },
        el('span', { class: 'big' }, '🗄️'),
        el('h2', {}, 'No cellars yet'),
        el('p', {}, 'Cellars keep separate places apart — a basement, a kitchen rack, an offsite locker.'));

  return mount(
    el('div', { class: 'page-head' },
      el('div', {}, el('h1', {}, 'Cellars'),
        el('p', {}, 'Every cellar on this account. Bottles live in exactly one at a time; you can move them between.')),
      el('button', { class: 'btn-primary', type: 'button', onClick: () => cellarForm() }, '+ New cellar')),
    list);
}

function cellarCard(cellar) {
  const capacityLine = cellar.capacity
    ? `${count(cellar.bottle_count)} of ${count(cellar.capacity)} · ${Math.round((100 * cellar.bottle_count) / cellar.capacity)}% full`
    : plural(cellar.bottle_count, 'bottle');

  return el('div', { class: 'bottle', style: 'grid-template-columns: 1fr auto; cursor:default' },
    el('div', {},
      el('div', { class: 'title' }, cellar.name,
        cellar.is_default ? el('span', { class: 'tag', style: 'margin-left:.5rem' }, 'default') : null),
      el('div', { class: 'meta' },
        cellar.location ? el('span', {}, cellar.location) : null,
        el('span', {}, capacityLine),
        cellar.total_cost ? el('span', {}, `${money(cellar.total_cost)} paid`) : null,
        cellar.oldest_vintage ? el('span', {}, `${cellar.oldest_vintage}–${cellar.newest_vintage}`) : null),
      cellar.description ? el('div', { class: 'hint', style: 'margin-top:.3rem' }, cellar.description) : null),
    el('div', { class: 'btn-row' },
      el('button', {
        class: 'btn-sm', type: 'button',
        onClick: () => { config.activeCellarId = cellar.id; refreshCellarSwitcher(); location.hash = '#/inventory'; },
      }, 'Open'),
      el('button', { class: 'btn-sm btn-ghost', type: 'button', onClick: () => cellarForm(cellar) }, 'Edit'),
      el('button', {
        class: 'btn-sm btn-danger', type: 'button',
        onClick: async () => {
          const ok = await confirmAction(
            `Delete ${cellar.name}?`,
            `This removes the cellar and all ${plural(cellar.bottle_count, 'bottle')} recorded in it. This cannot be undone.`,
          );
          if (!ok) return;
          try {
            await api.deleteCellar(cellar.id);
            if (config.activeCellarId === cellar.id) config.activeCellarId = null;
            toast(`Deleted ${cellar.name}`, 'ok');
            state.invalidate();
            await refreshCellarSwitcher();
            cellarsView();
          } catch (error) { toast(error.message, 'error'); }
        },
      }, 'Delete')));
}

function cellarForm(existing = null) {
  const name = el('input', { value: existing?.name || '', required: true, maxlength: '200', placeholder: 'Main Cellar' });
  const location = el('input', { value: existing?.location || '', maxlength: '300', placeholder: 'Basement, north wall' });
  const capacity = el('input', { type: 'number', min: '1', value: existing?.capacity ?? '', placeholder: '300' });
  const description = el('textarea', { maxlength: '2000', placeholder: 'What goes in here?' }, existing?.description || '');
  const isDefault = el('input', { type: 'checkbox', style: 'width:auto', checked: existing?.is_default || false });

  const save = el('button', { class: 'btn-primary', type: 'submit' }, existing ? 'Save changes' : 'Create cellar');

  const form = el('form', {
    onSubmit: async (event) => {
      event.preventDefault();
      if (!name.value.trim()) { toast('Give the cellar a name', 'error'); return; }
      save.disabled = true;
      const payload = {
        name: name.value.trim(),
        location: location.value.trim() || null,
        capacity: capacity.value ? Number(capacity.value) : null,
        description: description.value.trim() || null,
        is_default: isDefault.checked,
      };
      try {
        if (existing) await api.updateCellar(existing.id, payload);
        else {
          const created = await api.createCellar(payload);
          config.activeCellarId = created.id;
        }
        toast(existing ? 'Cellar updated' : 'Cellar created', 'ok');
        close();
        state.invalidate();
        await refreshCellarSwitcher();
        cellarsView();
      } catch (error) {
        toast(error.message, 'error');
        save.disabled = false;
      }
    },
  },
    field('Name', name),
    field('Location', location, 'Where it physically is — helps when you have more than one.'),
    el('div', { class: 'field-grid' },
      field('Capacity (bottles)', capacity, 'Optional. Drives the "% full" reading.')),
    field('Notes', description),
    el('label', { class: 'field', style: 'display:flex;gap:.5rem;align-items:center' },
      isDefault, el('span', { style: 'margin:0;text-transform:none;letter-spacing:0;font-size:.9rem' }, 'Make this the default cellar')),
    el('div', { class: 'btn-row' }, save,
      el('button', { class: 'btn-ghost', type: 'button', onClick: () => close() }, 'Cancel')));

  const close = modal(existing ? `Edit ${existing.name}` : 'New cellar', form);
}
