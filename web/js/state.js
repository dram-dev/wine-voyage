// Shared, short-lived caches. Cellars are read on nearly every view, so they
// are fetched once per navigation cycle rather than per view.

import { api } from './api.js';
import { config } from './config.js';

let cellarCache = null;
let cellarPromise = null;

export const state = {
  async cellars({ force = false } = {}) {
    if (force) { cellarCache = null; cellarPromise = null; }
    if (cellarCache) return cellarCache;
    if (!cellarPromise) {
      cellarPromise = api.listCellars()
        .then((rows) => { cellarCache = rows; return rows; })
        .finally(() => { cellarPromise = null; });
    }
    return cellarPromise;
  },

  /** The cellar the user is looking at: their stored choice, else the default. */
  activeCellar(cellars) {
    if (!cellars?.length) return null;
    const stored = cellars.find((c) => c.id === config.activeCellarId);
    const active = stored || cellars.find((c) => c.is_default) || cellars[0];
    if (config.activeCellarId !== active.id) config.activeCellarId = active.id;
    return active;
  },

  invalidate() { cellarCache = null; cellarPromise = null; },
};
