-- Wine Voyage schema (Postgres 16)

CREATE TABLE IF NOT EXISTS countries (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    emoji   TEXT,
    color   TEXT
);

CREATE TABLE IF NOT EXISTS regions (
    id          TEXT PRIMARY KEY,
    country_id  TEXT NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appellations (
    id          TEXT PRIMARY KEY,
    region_id   TEXT NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    grapes      TEXT[] NOT NULL DEFAULT '{}',
    style       TEXT,
    lat         NUMERIC(9, 6),
    lng         NUMERIC(9, 6)
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id          SERIAL PRIMARY KEY,
    wine_name   TEXT NOT NULL,
    region      TEXT,
    vintage     INTEGER,
    his_rating  INTEGER CHECK (his_rating BETWEEN 1 AND 5),
    her_rating  INTEGER CHECK (her_rating BETWEEN 1 AND 5),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trips (
    id              SERIAL PRIMARY KEY,
    appellation_id  TEXT NOT NULL REFERENCES appellations(id) ON DELETE CASCADE,
    visited         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS taste_profile (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    region      TEXT,
    grape       TEXT,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wineries (
    id              SERIAL PRIMARY KEY,
    appellation_id  TEXT NOT NULL REFERENCES appellations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    stars           NUMERIC(2, 1) CHECK (stars BETWEEN 0 AND 5),
    note            TEXT,
    source          TEXT NOT NULL DEFAULT 'curated',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_cache (
    cache_key   TEXT PRIMARY KEY,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days')
);
