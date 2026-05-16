# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Wine Voyage backend — a FastAPI + asyncpg + Postgres service intended to run on a Mac mini and serve a React frontend over Tailscale. AI-powered endpoints (sommelier suggestions, winery matches, seed generation) call Anthropic Claude via the Anthropic Python SDK.

## Running locally

```bash
# Setup once
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit ANTHROPIC_API_KEY

# Run migrations in order — they are NOT idempotent across versions
psql winevoyage -f sql/001_schema.sql
psql winevoyage -f sql/002_indexes.sql
psql winevoyage -f sql/003_top_rated.sql
psql winevoyage -f sql/004_votes.sql
psql winevoyage -f sql/005_geo.sql

# Seed (each step is independently optional / idempotent)
python -m scripts.seed_appellations                    # required first; loads data/appellations.json
python -m scripts.seed_wineries --dry-run              # AI; preview without API/writes
python -m scripts.seed_top_rated --limit 25            # AI; ranks AAVs + top 40 wineries/varietals/vintages
python -m scripts.seed_winery_geo --dry-run            # AI; backfills winery lat/lng

./run.sh                                               # starts uvicorn on 0.0.0.0:$PORT (default 8420)
```

There is no test suite, lint config, or build step. `python -m py_compile <path>` is the only syntax check used.

## Architecture

### Request pipeline

`server/main.py` is the FastAPI app entry point. It wires a single asyncpg pool (`server/db.py`) via the `lifespan` context manager, then mounts every router under `/api`. Routers in `server/routes/` are thin: each acquires the pool via `get_pool()`, runs SQL with parameterized queries, and returns plain dicts (FastAPI handles serialization).

The asyncpg pool is a process-wide singleton; never instantiate connections directly in request handlers. Scripts in `scripts/` use `asyncpg.connect(settings.database_url)` directly because they run outside the FastAPI lifespan.

### Data model layers

The schema grew in five migrations, each adding one cohesive feature on top of the last:

1. **`001_schema.sql`** — core domain: `countries → regions → appellations`, plus `journal_entries`, `trips`, `taste_profile`, `wineries`, `ai_cache`. The `wineries.stars` column uses `NUMERIC(2,1)` (1.0–5.0 in 0.5 increments).
2. **`002_indexes.sql`** — foreign-key and cache-expiry indexes.
3. **`003_top_rated.sql`** — adds `appellations.popularity_rank` plus `winery_varietals` and `winery_vintages` (per-winery rated picks). `winery_vintages.rating` is a 100-point critic scale; `winery_varietals.rating` is the 1–5 star scale.
4. **`004_votes.sql`** — polymorphic `votes` table keyed by `(target_type ∈ {winery, varietal, vintage}, target_id, client_id)`. There is **no FK** on `target_id` (impossible with polymorphic targets), so `votes.py` always calls `_target_exists` before insert to return a clean 404. Voting orphans on cascade-delete are accepted as a tradeoff.
5. **`005_geo.sql`** — adds `lat/lng` to `wineries` (appellations already had them) with partial indexes that only cover rows where coordinates are non-null.

### AI plumbing

`server/sommelier_client.py` is the only place that talks to Anthropic. It exposes `call_sommelier(prompt, max_tokens)` which always returns a dict (`{"error": "..."}` on any failure, never raises) and helpers `cache_get` / `cache_set` against the `ai_cache` table (30-day TTL). Routes and seed scripts both go through this client.

Cache keys are hashes built from the inputs (e.g. `hashlib.sha256(json.dumps({"a": appellation_id, "ids": sorted_ids}).encode())` in `wineries.py`). The model id is hardcoded in `sommelier_client.py`'s `SOMMELIER_MODEL` constant.

### Vote enrichment pattern

Several read endpoints surface vote tallies alongside their primary data:

- `GET /api/top-rated` enriches every winery / varietal / vintage in its response.
- `GET /api/wineries/{appellation_id}` enriches every winery.

Both call `load_votes_for_targets(pool, winery_ids=..., varietal_ids=..., vintage_ids=..., client_id=...)` from `server/routes/votes.py`. The helper runs all summary + per-client queries in parallel via `asyncio.gather`. When `client_id` is omitted, only aggregate `votes: {up, down, score}` is returned; when included, each entity also gets `my_vote: -1 | 1 | null`.

A shared `EMPTY_SUMMARY = {"up": 0, "down": 0, "score": 0}` constant lives in `votes.py` and is reused by both enriched endpoints — do not re-inline this literal.

### Geo / zoom level of detail

`GET /api/geo/features?north=&south=&east=&west=&zoom=` returns a GeoJSON FeatureCollection sized to the viewport. Thresholds in `server/routes/geo.py`:

- `zoom < 7` → appellation pins only.
- `7 ≤ zoom < 11` → + premium wineries (`stars >= 4.5`).
- `zoom ≥ 11` → + all wineries with coordinates.

Antimeridian-crossing bounding boxes (`west > east`) switch the longitude predicate from a BETWEEN range to a disjunction — handle this when adding new geo queries.

### Frontend contract

There is no frontend in this repo. CORS is wide open (`allow_origins=["*"]`) because Tailscale is expected to handle auth at the network layer. Identity is by `client_id` — a UUID the frontend stores in localStorage and passes as a request body field (votes) or query param (`/api/top-rated`, `/api/wineries/{id}`). There is no user/auth table.

## Seed data conventions

`data/appellations.json` mirrors the React app's `WINE_DATA` shape; the seed script is `ON CONFLICT DO UPDATE`, safe to re-run.

`data/popular_aavs.json` is a list of appellation IDs in popularity order — array index equals rank. The matching seed script (`seed_top_rated.py`) UPDATEs `popularity_rank`, deletes existing `source='ai'` wineries for the AAV, then re-inserts via Claude.

`data/top_rated_sample.json` and `data/top_rated_california_sample.json` are hand-curated payloads that match the exact `GET /api/top-rated` response shape. They exist so a frontend can be built without a live database.

## Conventions

- Routes return plain `dict` / `list[dict]`; let FastAPI handle JSON.
- `NUMERIC` columns come back as `decimal.Decimal` — wrap in `float(...)` before returning.
- Postgres array columns come back as Python lists but may be `None`; normalize with `list(row["grapes"]) if row["grapes"] else []`.
- Per-row `id` is always exposed in responses for vote and edit round-trips.
- Migrations are append-only — add `006_*.sql` for new schema, never edit existing migrations.

## What's intentionally absent

- No test suite, no linter config, no CI. Don't add these unless asked.
- No auth, no user table. `client_id` is the only identity primitive.
- No ORM. asyncpg + raw parameterized SQL throughout. Don't introduce SQLAlchemy.
- No request validation beyond Pydantic models on POST bodies. GET endpoints validate via FastAPI `Query(...)` constraints.
