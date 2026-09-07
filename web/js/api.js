// Thin API client. Every call carries the account id; when no backend is
// configured the request is served by the in-browser demo cellar instead, so
// the published Pages site is explorable before anyone stands a server up.

import { config } from './config.js';
import { demoRequest } from './demo.js';

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

async function request(method, path, { query = {}, body = null, timeout = 60000 } = {}) {
  if (config.usingDemo) return demoRequest(method, path, { query, body });

  const url = new URL(config.apiBase.replace(/\/+$/, '') + path);
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== '') url.searchParams.set(key, value);
  }

  // Label scans call a vision model and can genuinely take ~30s; everything
  // else should be fast, but one ceiling keeps the client from hanging.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : null,
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    if (error.name === 'AbortError') throw new ApiError('The request timed out.', 0, null);
    throw new ApiError(
      `Can't reach the API at ${config.apiBase}. Check that the server is running and reachable from this device.`,
      0, null,
    );
  }
  clearTimeout(timer);

  if (response.status === 204) return null;

  const text = await response.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { payload = { detail: text }; }

  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) ? detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
      : `Request failed (${response.status})`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

const account = () => config.accountId;

export const api = {
  health: () => request('GET', '/health'),

  // -- cellars --
  listCellars: () => request('GET', '/api/cellars', { query: { account_id: account() } }),
  createCellar: (data) => request('POST', '/api/cellars', { body: { account_id: account(), ...data } }),
  updateCellar: (id, data) => request('PATCH', `/api/cellars/${id}`, { query: { account_id: account() }, body: data }),
  deleteCellar: (id) => request('DELETE', `/api/cellars/${id}`, { query: { account_id: account() } }),
  cellarStats: (id) => request('GET', `/api/cellars/${id}/stats`, { query: { account_id: account() } }),

  // -- bottles --
  searchBottles: (params) => request('GET', '/api/bottles', { query: { account_id: account(), ...params } }),
  facets: (params) => request('GET', '/api/bottles/facets', { query: { account_id: account(), ...params } }),
  addBottle: (data) => request('POST', '/api/bottles', { body: { account_id: account(), ...data } }),
  getBottle: (id) => request('GET', `/api/bottles/${id}`, { query: { account_id: account() } }),
  updateBottle: (id, data) => request('PATCH', `/api/bottles/${id}`, { query: { account_id: account() }, body: data }),
  consumeBottle: (id, data) => request('POST', `/api/bottles/${id}/consume`, { body: { account_id: account(), ...data } }),
  moveBottle: (id, data) => request('POST', `/api/bottles/${id}/move`, { body: { account_id: account(), ...data } }),
  deleteBottle: (id) => request('DELETE', `/api/bottles/${id}`, { query: { account_id: account() } }),

  // -- label scanning --
  identifyLabel: (imageBase64, mediaType) => request('POST', '/api/labels/identify', {
    body: { image_base64: imageBase64, media_type: mediaType, account_id: account() },
    timeout: 90000,
  }),

  // -- scores, value, recommendations --
  scores: (wineId, refresh = false) => request('GET', `/api/wines/${wineId}/scores`, { query: { refresh: refresh || '' }, timeout: 90000 }),
  valuation: (wineId, refresh = false) => request('GET', `/api/wines/${wineId}/valuation`, { query: { refresh: refresh || '' }, timeout: 90000 }),
  similar: (wineId) => request('GET', `/api/wines/${wineId}/similar`, { query: { account_id: account() }, timeout: 90000 }),
  recommendations: (data) => request('POST', '/api/recommendations', { body: { account_id: account(), ...data }, timeout: 90000 }),
};
