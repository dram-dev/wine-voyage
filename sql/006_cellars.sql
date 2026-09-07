-- Cellar inventory: accounts, cellars, canonical wines, bottles, and history.
--
-- Identity follows the pattern votes.client_id already established: an
-- `account_id` is a stable UUID the frontend stores in localStorage. There is
-- no password auth — the id IS the account. Every cellar hangs off one.
--
-- `wines` is a canonical, account-independent wine identity (producer + cuvée +
-- vintage + bottle size). Two people holding the same wine point at the same
-- row, so critic scores, valuations, and "you may also like" are computed once
-- and shared. `cellar_bottles` is the per-account holding of that wine.

CREATE TABLE IF NOT EXISTS cellars (
    id          SERIAL PRIMARY KEY,
    account_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    location    TEXT,
    description TEXT,
    capacity    INTEGER CHECK (capacity > 0),
    is_default  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (account_id, name)
);

-- At most one default cellar per account.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cellars_one_default
    ON cellars (account_id)
    WHERE is_default;

CREATE INDEX IF NOT EXISTS idx_cellars_account ON cellars (account_id);

CREATE TABLE IF NOT EXISTS wines (
    id              SERIAL PRIMARY KEY,
    -- natural_key = normalized producer|wine_name|vintage|size, built in Python
    -- (see server/wine_identity.py). Drives dedupe across accounts.
    natural_key     TEXT NOT NULL UNIQUE,
    producer        TEXT NOT NULL,
    wine_name       TEXT,
    vintage         INTEGER CHECK (vintage BETWEEN 1800 AND 2100),  -- NULL = non-vintage
    varietals       TEXT[] NOT NULL DEFAULT '{}',
    wine_type       TEXT CHECK (wine_type IN ('red','white','rose','sparkling','dessert','fortified','other')),
    country         TEXT,
    region          TEXT,
    appellation     TEXT,
    appellation_id  TEXT REFERENCES appellations(id) ON DELETE SET NULL,
    bottle_size_ml  INTEGER NOT NULL DEFAULT 750 CHECK (bottle_size_ml > 0),
    abv             NUMERIC(4, 2) CHECK (abv BETWEEN 0 AND 100),
    drink_from      INTEGER CHECK (drink_from BETWEEN 1800 AND 2200),
    drink_to        INTEGER CHECK (drink_to BETWEEN 1800 AND 2200),
    label_image_url TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wines_producer   ON wines (lower(producer));
CREATE INDEX IF NOT EXISTS idx_wines_vintage    ON wines (vintage);
CREATE INDEX IF NOT EXISTS idx_wines_country    ON wines (country);
CREATE INDEX IF NOT EXISTS idx_wines_region     ON wines (region);
CREATE INDEX IF NOT EXISTS idx_wines_varietals  ON wines USING GIN (varietals);
CREATE INDEX IF NOT EXISTS idx_wines_appellation_id ON wines (appellation_id);

CREATE TABLE IF NOT EXISTS cellar_bottles (
    id              SERIAL PRIMARY KEY,
    cellar_id       INTEGER NOT NULL REFERENCES cellars(id) ON DELETE CASCADE,
    wine_id         INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
    bin             TEXT,                       -- rack / slot within the cellar
    purchase_price  NUMERIC(10, 2) CHECK (purchase_price >= 0),
    purchase_date   DATE,
    purchase_source TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD',
    my_rating       NUMERIC(4, 1) CHECK (my_rating BETWEEN 0 AND 100),
    notes           TEXT,
    status          TEXT NOT NULL DEFAULT 'in_cellar'
                    CHECK (status IN ('in_cellar','consumed','gifted','sold','lost')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One lot per (cellar, wine, bin): re-adding the same wine to the same slot
    -- bumps quantity instead of creating a duplicate row.
    UNIQUE (cellar_id, wine_id, bin)
);

CREATE INDEX IF NOT EXISTS idx_cellar_bottles_cellar ON cellar_bottles (cellar_id);
CREATE INDEX IF NOT EXISTS idx_cellar_bottles_wine   ON cellar_bottles (wine_id);
CREATE INDEX IF NOT EXISTS idx_cellar_bottles_status ON cellar_bottles (cellar_id, status);

-- Append-only history so the cellar can answer "what did we drink in 2025?"
CREATE TABLE IF NOT EXISTS bottle_events (
    id              SERIAL PRIMARY KEY,
    bottle_id       INTEGER NOT NULL REFERENCES cellar_bottles(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL
                    CHECK (event_type IN ('added','consumed','gifted','sold','lost','moved','adjusted')),
    quantity_delta  INTEGER NOT NULL DEFAULT 0,
    note            TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bottle_events_bottle ON bottle_events (bottle_id, occurred_at DESC);

-- Critic / community scores per wine. `source_kind` is the honesty column:
-- 'critic' and 'community' rows come from a real provider (see
-- server/score_providers.py); 'ai_estimate' rows are model-generated and must
-- be labelled as estimates everywhere they surface.
CREATE TABLE IF NOT EXISTS wine_scores (
    id           SERIAL PRIMARY KEY,
    wine_id      INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    source       TEXT NOT NULL,
    source_kind  TEXT NOT NULL CHECK (source_kind IN ('critic','community','ai_estimate')),
    score        NUMERIC(5, 1),
    scale        TEXT NOT NULL DEFAULT '100',   -- '100', '20', '5'
    reviewer     TEXT,
    review       TEXT,
    url          TEXT,
    confidence   NUMERIC(3, 2) CHECK (confidence BETWEEN 0 AND 1),
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (wine_id, source)
);

CREATE INDEX IF NOT EXISTS idx_wine_scores_wine ON wine_scores (wine_id);

CREATE TABLE IF NOT EXISTS wine_valuations (
    id           SERIAL PRIMARY KEY,
    wine_id      INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    source       TEXT NOT NULL,
    source_kind  TEXT NOT NULL CHECK (source_kind IN ('market','ai_estimate')),
    low          NUMERIC(10, 2),
    mid          NUMERIC(10, 2),
    high         NUMERIC(10, 2),
    currency     TEXT NOT NULL DEFAULT 'USD',
    note         TEXT,
    confidence   NUMERIC(3, 2) CHECK (confidence BETWEEN 0 AND 1),
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (wine_id, source)
);

CREATE INDEX IF NOT EXISTS idx_wine_valuations_wine ON wine_valuations (wine_id);

-- Label photo scans, keyed by image hash so re-scanning the same shot (or the
-- same bottle from two phones) is free.
CREATE TABLE IF NOT EXISTS label_scans (
    id           SERIAL PRIMARY KEY,
    image_sha256 TEXT NOT NULL UNIQUE,
    account_id   TEXT,
    result       JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
