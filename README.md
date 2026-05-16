# Wine Voyage Backend

FastAPI + Postgres backend for the Wine Voyage app. Designed to run on a Mac mini and serve a React frontend over Tailscale.

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

## Troubleshooting

- **`asyncpg.exceptions.InvalidCatalogNameError`** — run `createdb winevoyage`.
- **`401` from Claude** — `ANTHROPIC_API_KEY` is missing or wrong in `.env`.
- **`{"error": "invalid_json", ...}` from sommelier** — the model returned non-JSON. The raw text is in the `raw` field; tighten the prompt.
- **Port 8420 in use** — set `PORT` in `.env` and update the frontend.
- **CORS errors in browser** — server allows `*`; check the URL the frontend is hitting.
- **Wineries seed dies partway** — re-running it appends duplicates (no upsert key). Delete rows for affected appellation_ids before retrying.
