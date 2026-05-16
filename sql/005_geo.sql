-- Geo coordinates for wineries (appellations already carry lat/lng).
-- The /api/geo/features endpoint queries by bounding box + zoom, so we
-- index the coordinates as a partial index (only rows that actually have
-- coordinates participate).

ALTER TABLE wineries
    ADD COLUMN IF NOT EXISTS lat NUMERIC(9, 6),
    ADD COLUMN IF NOT EXISTS lng NUMERIC(9, 6);

CREATE INDEX IF NOT EXISTS idx_wineries_geo
    ON wineries (lat, lng)
    WHERE lat IS NOT NULL AND lng IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_appellations_geo
    ON appellations (lat, lng)
    WHERE lat IS NOT NULL AND lng IS NOT NULL;
