-- Value tracking: price history per wine, and cellar value over time.
--
-- 006 gave each wine a current valuation, but it upserts in place, so the old
-- number is gone the moment a new one lands — you can see what the cellar is
-- worth, never what it was worth. These two tables are the record:
--
--   wine_valuation_history   append-only, one row per observed price
--   cellar_value_snapshots   one row per cellar per day, so the value chart
--                            is a single indexed read instead of a re-walk of
--                            every bottle's price history

-- A hand-entered price beats a market feed beats the model's guess. `manual`
-- is new here; the ranking lives in server/valuation.py so every query orders
-- valuations the same way.
ALTER TABLE wine_valuations DROP CONSTRAINT IF EXISTS wine_valuations_source_kind_check;
ALTER TABLE wine_valuations ADD CONSTRAINT wine_valuations_source_kind_check
    CHECK (source_kind IN ('manual', 'market', 'ai_estimate'));

CREATE TABLE IF NOT EXISTS wine_valuation_history (
    id           SERIAL PRIMARY KEY,
    wine_id      INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    source       TEXT NOT NULL,
    source_kind  TEXT NOT NULL CHECK (source_kind IN ('manual', 'market', 'ai_estimate')),
    low          NUMERIC(10, 2),
    mid          NUMERIC(10, 2),
    high         NUMERIC(10, 2),
    currency     TEXT NOT NULL DEFAULT 'USD',
    note         TEXT,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wine_valuation_history_wine
    ON wine_valuation_history (wine_id, recorded_at DESC);

-- One snapshot per cellar per day. Re-running a valuation the same day updates
-- that day's row rather than stacking duplicate points on the chart.
CREATE TABLE IF NOT EXISTS cellar_value_snapshots (
    id              SERIAL PRIMARY KEY,
    cellar_id       INTEGER NOT NULL REFERENCES cellars(id) ON DELETE CASCADE,
    captured_on     DATE NOT NULL DEFAULT CURRENT_DATE,
    bottle_count    INTEGER NOT NULL DEFAULT 0,
    lot_count       INTEGER NOT NULL DEFAULT 0,
    cost_basis      NUMERIC(14, 2),
    market_value    NUMERIC(14, 2),
    valued_bottles  INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'USD',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cellar_id, captured_on)
);

CREATE INDEX IF NOT EXISTS idx_cellar_value_snapshots_cellar
    ON cellar_value_snapshots (cellar_id, captured_on);
