-- Upvote / downvote feature for wineries, varietals, and vintages.
-- One polymorphic table keyed by (target_type, target_id, client_id). A given
-- client casts at most one vote per target — re-voting upserts, removal is a
-- DELETE. `experience` carries the optional tasting note that motivated the
-- vote ("based on experience").

CREATE TABLE IF NOT EXISTS votes (
    id              SERIAL PRIMARY KEY,
    target_type     TEXT NOT NULL CHECK (target_type IN ('winery', 'varietal', 'vintage')),
    target_id       INTEGER NOT NULL,
    client_id       TEXT NOT NULL,
    value           SMALLINT NOT NULL CHECK (value IN (-1, 1)),
    experience      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (target_type, target_id, client_id)
);

CREATE INDEX IF NOT EXISTS idx_votes_target      ON votes (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_votes_client      ON votes (client_id);
CREATE INDEX IF NOT EXISTS idx_votes_target_val  ON votes (target_type, target_id, value);
