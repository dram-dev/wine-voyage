/* Browser adapters for the two host APIs the original artifact relied on.

   - Persistence was `window.storage`, which only exists inside the Claude
     artifact runtime. In a browser we use localStorage; the async signatures
     are kept so the component code is unchanged.
   - AI calls went straight to api.anthropic.com from the page, which cannot
     work in a browser (no key, and CORS blocks it). They now go through the
     backend's POST /api/sommelier, which holds the key and caches responses
     in Postgres. */

// Empty base = same origin. `npm run dev` proxies /api to localhost:8420;
// production builds set VITE_API_BASE to the deployed API root.
const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/+$/, "");

export const apiBase = API_BASE;

export const store = async (k, v) => {
  try {
    localStorage.setItem(k, JSON.stringify(v));
  } catch (e) {
    /* quota or private-mode failure — the in-memory state stays correct */
  }
};

export const read = async (k) => {
  try {
    const r = localStorage.getItem(k);
    return r ? JSON.parse(r) : null;
  } catch (e) {
    return null;
  }
};

export async function askAI(prompt, cacheKey) {
  try {
    const res = await fetch(`${API_BASE}/api/sommelier`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cache_key: cacheKey, prompt }),
    });
    if (res.status === 404)
      throw new Error("No sommelier API reachable — set VITE_API_BASE to your Wine Voyage server.");
    if (!res.ok) throw new Error(`Sommelier API returned ${res.status}`);
    const d = await res.json();
    const r = d?.response || {};
    if (r.error)
      throw new Error(r.error === "invalid_json" ? "The sommelier returned malformed JSON." : r.error);
    return r;
  } catch (e) {
    const msg = e instanceof TypeError ? "Can't reach the sommelier API." : e.message || String(e);
    return { _error: msg };
  }
}
