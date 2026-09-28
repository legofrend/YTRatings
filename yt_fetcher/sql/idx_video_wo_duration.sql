-- Partial index for video-detail backfill (null duration keyset scan).
-- Run with CONCURRENTLY on live DB (cannot wrap in a transaction).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_video_wo_duration
  ON video (video_id)
  WHERE status = 1 AND duration IS NULL;
