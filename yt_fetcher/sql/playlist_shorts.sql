-- UUSH playlist mirror: one row per Short video_id (ingest from YouTube API).
-- Apply video.is_short locally from this table without extra API calls.

CREATE TABLE IF NOT EXISTS playlist_shorts (
    id SERIAL PRIMARY KEY,
    video_id TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL REFERENCES channel (channel_id),
    title TEXT,
    published_at TIMESTAMP NOT NULL,
    published_at_period DATE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_playlist_shorts_channel_id
    ON playlist_shorts (channel_id);

CREATE INDEX IF NOT EXISTS idx_playlist_shorts_channel_published
    ON playlist_shorts (channel_id, published_at);

CREATE INDEX IF NOT EXISTS idx_playlist_shorts_published_period
    ON playlist_shorts (published_at_period);

ALTER TABLE channel
    ADD COLUMN IF NOT EXISTS last_shorts_fetch_dt TIMESTAMP DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_channel_last_shorts_fetch_dt
    ON channel (last_shorts_fetch_dt);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_set_updated_at_playlist_shorts ON playlist_shorts;
CREATE TRIGGER trigger_set_updated_at_playlist_shorts
BEFORE UPDATE ON playlist_shorts
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
