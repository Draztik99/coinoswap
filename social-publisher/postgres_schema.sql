-- CoinoSwap direct Facebook: durable, single-authority publication ledger.
-- Apply only to an explicitly configured managed PostgreSQL database.
-- Development feature branch: no database is provisioned or modified here.

CREATE TABLE IF NOT EXISTS coinoswap_social_publications (
    platform TEXT NOT NULL CHECK (platform IN ('facebook', 'x', 'instagram')),
    date_sast DATE NOT NULL,
    campaign_key TEXT NOT NULL CHECK (campaign_key ~ '^[a-z0-9_-]{2,60}$'),
    image_sha256 CHAR(64) NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
    request_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('RESERVED', 'SENDING', 'UNKNOWN', 'PUBLISHED', 'FAILED_PRE_SEND')
    ),
    provider_post_id TEXT,
    public_url TEXT,
    source TEXT NOT NULL DEFAULT 'direct' CHECK (source IN ('direct', 'metricool')),
    last_error TEXT,
    created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform, date_sast, campaign_key),
    CHECK (state <> 'PUBLISHED' OR (provider_post_id IS NOT NULL AND public_url IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS coinoswap_social_publications_state_idx
    ON coinoswap_social_publications (platform, state, updated_at_utc);
