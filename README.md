# Wine Voyage Backend

FastAPI + Postgres backend for the Wine Voyage app, plus a static cellar
frontend published to GitHub Pages. Designed to run on a Mac mini and be
reachable from a phone over Tailscale.

## Stack

- Python 3.12, FastAPI, asyncpg
- Postgres 16
- Anthropic Claude (Sonnet) for sommelier and recommendation endpoints

## Layout

```
server/        FastAPI app and routers
sql/           Schema + indexes
scripts/       One-shot seed scripts
data/          Seed JSON (you edit this)
web/           Static cellar frontend (deployed to GitHub Pages)
```

## Setup

```bash
# 1. Postgres
brew install postgresql@16
brew services start postgresql@16
createdb winevoyage

# 2. Python env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY

# 4. Migrations
psql winevoyage -f sql/001_schema.sql
psql winevoyage -f sql/002_indexes.sql
psql winevoyage -f sql/003_top_rated.sql
psql winevoyage -f sql/004_votes.sql
psql winevoyage -f sql/005_geo.sql
psql winevoyage -f sql/006_cellars.sql

# 5. Seed appellations (after editing data/appellations.json)
python -m scripts.seed_appellations

# 6. (Optional) Seed wineries via AI — costs ~$2-3
python -m scripts.seed_wineries --dry-run   # preview
python -m scripts.seed_wineries             # real run

# 7. (Optional) Rank popular AAVs + seed top 40 wineries/varietals/vintages
python -m scripts.seed_top_rated --dry-run --limit 25   # preview
python -m scripts.seed_top_rated                        # full pass (1000 AAVs)

# 8. (Optional) Backfill lat/lng on wineries for the map
python -m scripts.seed_winery_geo --dry-run --limit-aavs 25
python -m scripts.seed_winery_geo

# 9. Run the server
./run.sh
```

The server listens on `0.0.0.0:8420` by default. Override with `PORT` in `.env`.

## API

All endpoints are under `/api`. CORS is open to `*`.

### Appellations
- `GET  /api/appellations` — list all (joined with region + country)
- `GET  /api/appellations/{id}` — full detail

### Journal
- `GET    /api/journal`
- `POST   /api/journal` — body: `{wine_name, region?, vintage?, his_rating?, her_rating?, notes?}`
- `DELETE /api/journal/{id}`

### Trips
- `GET    /api/trips`
- `POST   /api/trips` — body: `{appellation_id}`
- `PATCH  /api/trips/{id}` — body: `{visited?: bool}` (omit to toggle)
- `DELETE /api/trips/{id}`

### Taste profile (reference winemakers)
- `GET    /api/taste`
- `POST   /api/taste` — body: `{name, region?, grape?, notes?}`
- `DELETE /api/taste/{id}`

### Sommelier (cached AI)
- `POST /api/sommelier` — body: `{cache_key, prompt, max_tokens?}`
  - Hits `ai_cache` first; misses call Claude with a strict JSON system prompt.

### Wineries
- `GET  /api/wineries/{appellation_id}` — curated list from the DB
- `POST /api/wineries/match` — body: `{appellation_id, taste_profile_ids: int[]}`
  - Generates AI matches against the user's saved taste profile. Cached by hash of `(appellation_id + sorted taste_profile_ids)`.

### Top-rated (popularity-ranked AAVs)
- `GET /api/top-rated?limit=1000&per_appellation=40&client_id=<uuid>`
  - Returns the world's most popular AAVs (capped at 1000), each with its
    top-rated wineries and each winery's top-rated varietals and vintages.
  - `limit` and `per_appellation` clamp to `[1, 1000]` and `[1, 40]` respectively.
  - Reads from `appellations.popularity_rank` (set by `scripts/seed_top_rated.py`).
  - Each winery / varietal / vintage carries a `votes: {up, down, score}` summary;
    when `client_id` is passed, also includes `my_vote: -1 | 1 | null`.

### Geo / map
- `GET /api/geo/features?north=&south=&east=&west=&zoom=&limit=1500`
  - Returns a GeoJSON `FeatureCollection` of appellation and winery pins
    inside the viewport. Level of detail scales with zoom:
    - `zoom < 7`  — appellations only (continental view).
    - `7-10`      — appellations + premium wineries (`stars >= 4.5`).
    - `zoom >= 11` — appellations + all wineries with coordinates.
  - Bounding boxes that wrap the antimeridian (`west > east`) are handled.
- `GET /api/geo/appellation/{appellation_id}`
  - All wineries with coordinates for one AAV, plus the appellation centre.

### Votes (upvote / downvote based on experience)
- `POST /api/votes` — body: `{target_type, target_id, value, client_id, experience?}`
  - `target_type` ∈ `winery | varietal | vintage`, `value` ∈ `-1 | 1`.
  - Upserts the client's vote on the target (re-voting changes direction or note).
  - `experience` is the optional tasting note that motivated the vote.
- `DELETE /api/votes` — body: `{target_type, target_id, client_id}` — removes the vote.
- `GET  /api/votes/summary?target_type=winery&target_ids=1,2,3` — aggregate counts.
- `GET  /api/votes/mine?client_id=<uuid>&target_type=winery&target_ids=1,2,3`
  - Returns this client's votes (value + experience) for the listed targets.
- `GET /api/wineries/{appellation_id}?client_id=<uuid>` — winery listing now
  carries `votes` and `my_vote` (when `client_id` is passed).

### Cellars (inventory)

Identity is an `account_id` — a UUID the frontend keeps in localStorage, the
same pattern `votes.client_id` uses. There is no password auth: holding the id
is holding the account, and every cellar endpoint scopes to it. Anything asking
for another account's data gets a 404, not a 403.

- `GET    /api/cellars?account_id=` — every cellar on the account, each with a
  bottle/lot/cost rollup.
- `POST   /api/cellars` — body: `{account_id, name, location?, description?, capacity?, is_default?}`
  - The first cellar on an account becomes the default automatically. Duplicate
    names on one account return 409.
- `PATCH  /api/cellars/{id}?account_id=` — partial update. Setting `is_default`
  clears it on the account's other cellars.
- `DELETE /api/cellars/{id}?account_id=` — removes the cellar and its bottles.
- `GET    /api/cellars/{id}/stats?account_id=` — dashboard rollup: bottle and lot
  counts, amount paid, estimated market value, capacity used, vintage span,
  bottles drunk in the last year, and breakdowns by type, varietal, vintage,
  region, and drink window.

### Bottles

A bottle row is a **lot**: N identical bottles of one wine in one bin of one
cellar. Re-adding the same wine to the same bin bumps the quantity rather than
creating a duplicate row.

- `GET /api/bottles?account_id=` — search, filter, and sort. All optional:
  - scope: `cellar_id` (omit to search every cellar), `status` (default `in_cellar`), `include_empty`
  - text: `q` — matches producer, cuvée, region, appellation, country, bin, and varietals
  - structured: `vintage_min`, `vintage_max`, `varietal`, `country`, `region`,
    `producer`, `wine_type`, `bin`, `drink_window`, `min_score`, `min_price`, `max_price`
  - ordering: `sort` (see below), `order` (`asc`/`desc`, NULLs always last)
  - paging: `limit` (≤500), `offset`. The response carries the unpaged `total`.
  - `sort` ∈ `added, vintage, producer, name, varietal, region, country, quantity,
    price, value, score, my_rating, drink_from, bin` — a whitelist, so the value
    never reaches the query as SQL. An unknown key is a 400.
- `GET /api/bottles/facets?account_id=&cellar_id=` — distinct varietals,
  countries, regions, producers, types, vintages, and bins with bottle counts,
  so the filter UI is built from what is actually in the cellar.
- `POST /api/bottles` — body: `{account_id, cellar_id, wine: {...}, quantity?, bin?,
  purchase_price?, purchase_date?, purchase_source?, currency?, my_rating?, notes?}`
  - `wine` needs only `producer`; everything else is optional. The wine is
    deduped against the canonical `wines` table (see below).
- `GET    /api/bottles/{id}?account_id=` — detail plus the lot's event history.
- `PATCH  /api/bottles/{id}?account_id=` — partial update.
- `POST   /api/bottles/{id}/consume` — body: `{account_id, quantity?, disposition?, my_rating?, note?}`
  - `disposition` ∈ `consumed | gifted | sold | lost`. Decrements the lot and
    appends a `bottle_events` row. Over-consuming returns 409.
- `POST   /api/bottles/{id}/move` — body: `{account_id, to_cellar_id, quantity?, bin?}`
  - Moves all or part of a lot to another cellar on the same account.
- `DELETE /api/bottles/{id}?account_id=`

**Wine identity.** `wines` is account-independent: producer, cuvée, vintage, and
bottle size, normalized (accents folded, punctuation dropped, lowercased) into a
`natural_key`. "Château Léoville-Barton" and "Chateau Leoville Barton" resolve to
one row, so scores and valuations are fetched once and shared. Re-scanning a
label fills in fields the stored row is missing rather than overwriting what is
already known.

### Label recognition

- `POST /api/labels/identify` — body: `{image_base64, media_type?, account_id?, refresh?}`
  - `image_base64` accepts raw base64 or a full `data:` URL. JPEG, PNG, WebP,
    and GIF up to 5MB (the frontend downscales before uploading).
  - Returns the add-bottle fields read off the label — producer, cuvée, vintage,
    varietals, type, country, region, appellation, size, ABV, drink window —
    plus `confidence`, per-field `field_confidence`, and an `estimated_value`.
  - Results are cached by SHA-256 of the image bytes; `refresh: true` bypasses it.
  - `readable: false` means the photo could not be identified. `needs_review` is
    always true: the result is a pre-filled form, never a silent save.

### Scores, valuation, and recommendations

- `GET /api/wines/{id}/scores?refresh=` — every score on file, best source first,
  plus a `consensus` average across 100-point scores.
- `GET /api/wines/{id}/valuation?refresh=` — per-bottle low/mid/high value range.
- `GET /api/wines/{id}/similar?account_id=` — "you may also like" for one wine.
- `POST /api/recommendations` — body: `{account_id, cellar_id?, count?, price_ceiling?, note?}`
  - Suggestions reasoned over the whole cellar (top producers, varietals, and
    your own ratings) plus the saved taste profile. Anything you already own is
    flagged `already_owned` rather than suggested blind.

**On score provenance.** Wine Spectator, Wine Advocate, Vinous, Wine-Searcher,
and CellarTracker are all behind paid or partner-only APIs, so this app ships
with **no live score or price provider wired up**. What it ships is the seam:
implement `ScoreProvider` / `ValuationProvider` in `server/score_providers.py`,
append it to the registry, and real data starts flowing — ranked above the
fallback. Until then, scores and valuations are **model estimates**, stored with
`source_kind = 'ai_estimate'` and surfaced with an `estimate` badge and a
disclaimer everywhere they appear. They are a starting point, not a citation,
and should not be used to insure or sell a bottle.

## The cellar frontend (GitHub Pages)

`web/` is a static site — plain HTML, CSS, and ES modules, no build step, no
dependencies. `.github/workflows/pages.yml` publishes it on every push to `main`
that touches `web/`.

**One-time repo setup:** Settings → Pages → Build and deployment → Source:
**GitHub Actions**. The first push to `main` then publishes to
`https://<owner>.github.io/<repo>/`.

To work on it locally, any static server will do:

```bash
python3 -m http.server 8899 --directory web
# then open http://localhost:8899/#/dashboard
```

### How the two halves connect

GitHub Pages serves static files only, so the site holds no data and no secrets
— it talks to the FastAPI server *you* run. The API base URL is a setting, not a
build constant:

- Open **Settings** in the app and enter your API base (e.g.
  `http://mac-mini.tail-xxxx.ts.net:8420`), then **Test connection**.
- Or open the site with `?api=<url>&account=<id>` once — it is stored and the
  parameters are stripped from the URL. The Settings page generates that link,
  which is the quickest way to set a phone up.
- With no API configured, the site runs against a built-in **sample cellar** so
  the page is explorable rather than blank. Changes there are not saved.

**Mixed content.** The Pages site is served over HTTPS, so browsers block calls
to a plain `http://` API. A Tailscale HTTPS hostname (`tailscale cert`), a
reverse proxy with a certificate, or serving `web/` locally all avoid this. This
is a browser rule, not something the app can work around.

**Account ids are bearer tokens.** Anyone with the id can read and change that
account's cellars. Share the setup link only with people you want in your cellar.

### What the frontend does

- **Dashboard** — bottle and lot counts, amount paid vs. estimated value,
  capacity used, vintage span, and breakdowns by varietal, region, type, and
  vintage. The drinking-window panel links straight into a filtered inventory.
- **Inventory** — free-text search plus facet filters (varietal, region,
  country, type, drink window, bin, vintage range) and 14 sort keys. Filter
  state lives in the URL hash, so a filtered view is linkable and survives a
  reload. Scope toggles between the active cellar and all of them.
- **Bottle sheet** — the wine's facts, score comparison across sources, value
  range, "you may also like", full event history, and the actions: drink, move
  between cellars, edit, remove.
- **Scan** — photograph a label (camera on mobile, file picker or live
  viewfinder on desktop). The image is downscaled in-browser to a 1600px JPEG
  before upload, then the add-bottle form arrives pre-filled with confidence
  shown for anything shaky. Nothing is saved until you confirm.
- **Discover** — buy-next suggestions reasoned over the whole cellar.
- **Cellars** — create, edit, delete, and set the default.

## Seed data shape

`data/appellations.json` mirrors the React app's `WINE_DATA`:

```json
{
  "countries": [
    {
      "id": "fr",
      "name": "France",
      "emoji": "🇫🇷",
      "color": "#7c3aed",
      "regions": [
        {
          "id": "burgundy",
          "name": "Burgundy",
          "appellations": [
            {
              "id": "chambolle-musigny",
              "name": "Chambolle-Musigny",
              "grapes": ["Pinot Noir"],
              "style": "Elegant red",
              "lat": 47.187,
              "lng": 4.952
            }
          ]
        }
      ]
    }
  ]
}
```

The seed script uses `ON CONFLICT DO UPDATE` — running it twice is safe.

## Tailscale deployment

Tailscale exposes the Mac mini as `mac-mini.tail-xxxx.ts.net` automatically. Point the React frontend at:

```
http://mac-mini.tail-xxxx.ts.net:8420/api
```

No DNS or TLS setup required — Tailscale handles auth at the network layer. Open the firewall on port 8420 only on the `tailscale0` interface if you want to be strict about it.

For autostart on boot, create a launchd plist that runs `./run.sh`, or use `pm2 start ./run.sh --name winevoyage`.

## Verification

```bash
# tables exist
psql winevoyage -c "\dt"

# appellation count
curl -s localhost:8420/api/appellations | jq length

# journal create + list
curl -s -XPOST -H 'content-type: application/json' \
  -d '{"wine_name":"Test 2018","his_rating":4,"her_rating":5}' \
  localhost:8420/api/journal
curl -s localhost:8420/api/journal | jq

# sommelier
curl -s -XPOST -H 'content-type: application/json' \
  -d '{"cache_key":"test:hello","prompt":"Return {\"hello\":\"world\"}."}' \
  localhost:8420/api/sommelier | jq
```

### Cellar smoke test

`scripts/smoke_cellar.py` exercises the whole inventory surface — cellars,
bottles, search/sort/filter, facets, consume, move, history, stats, and
cross-account isolation — against a real database, in-process (no server
needed). It creates and then deletes its own account.

```bash
pip install httpx                     # test-only dependency
DATABASE_URL=postgresql://localhost/winevoyage python -m scripts.smoke_cellar
```

It prints a PASS/FAIL line per check and exits non-zero if any fail.

## Troubleshooting

- **`asyncpg.exceptions.InvalidCatalogNameError`** — run `createdb winevoyage`.
- **`401` from Claude** — `ANTHROPIC_API_KEY` is missing or wrong in `.env`.
- **`{"error": "invalid_json", ...}` from sommelier** — the model returned non-JSON. The raw text is in the `raw` field; tighten the prompt.
- **Port 8420 in use** — set `PORT` in `.env` and update the frontend.
- **CORS errors in browser** — server allows `*`; check the URL the frontend is hitting.
- **Wineries seed dies partway** — re-running it appends duplicates (no upsert key). Delete rows for affected appellation_ids before retrying.
