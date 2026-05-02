-- Wine Voyage indexes

CREATE INDEX IF NOT EXISTS idx_regions_country_id      ON regions (country_id);
CREATE INDEX IF NOT EXISTS idx_appellations_region_id  ON appellations (region_id);
CREATE INDEX IF NOT EXISTS idx_trips_appellation_id    ON trips (appellation_id);
CREATE INDEX IF NOT EXISTS idx_wineries_appellation_id ON wineries (appellation_id);
CREATE INDEX IF NOT EXISTS idx_ai_cache_expires_at     ON ai_cache (expires_at);
