-- Partial index for apply-is-short / null is_short scans (active videos only).
-- Run with CONCURRENTLY on live DB (cannot wrap in a transaction).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_video_is_short_null
  ON video (video_id)
  WHERE is_short IS NULL AND status = 1;
