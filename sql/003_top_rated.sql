-- Top-rated wineries / varietals / vintages for the world's most popular appellations.
-- A "popularity_rank" of 1..N orders the most popular AAVs (Appellation d'Aire de Vinification);
-- the API surfaces the top 1000 ranked entries together with the top 40 rated
-- producers, varietals, and vintages associated with each one.

ALTER TABLE appellations
    ADD COLUMN IF NOT EXISTS popularity_rank INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_appellations_popularity_rank
    ON appellations (popularity_rank)
    WHERE popularity_rank IS NOT NULL;

CREATE TABLE IF NOT EXISTS winery_vintages (
    id              SERIAL PRIMARY KEY,
    winery_id       INTEGER NOT NULL REFERENCES wineries(id) ON DELETE CASCADE,
    vintage         INTEGER NOT NULL CHECK (vintage BETWEEN 1800 AND 2100),
    rating          NUMERIC(3, 1) CHECK (rating BETWEEN 0 AND 100),
    note            TEXT,
    source          TEXT NOT NULL DEFAULT 'ai',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (winery_id, vintage)
);

CREATE TABLE IF NOT EXISTS winery_varietals (
    id              SERIAL PRIMARY KEY,
    winery_id       INTEGER NOT NULL REFERENCES wineries(id) ON DELETE CASCADE,
    varietal        TEXT NOT NULL,
    rating          NUMERIC(2, 1) CHECK (rating BETWEEN 0 AND 5),
    note            TEXT,
    source          TEXT NOT NULL DEFAULT 'ai',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (winery_id, varietal)
);

CREATE INDEX IF NOT EXISTS idx_winery_vintages_winery_id   ON winery_vintages (winery_id);
CREATE INDEX IF NOT EXISTS idx_winery_varietals_winery_id  ON winery_varietals (winery_id);
CREATE INDEX IF NOT EXISTS idx_winery_vintages_rating      ON winery_vintages (rating DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_winery_varietals_rating     ON winery_varietals (rating DESC NULLS LAST);
