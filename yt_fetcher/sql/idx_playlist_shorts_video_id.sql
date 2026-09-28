-- Speeds up apply-is-short set_false NOT EXISTS (ps.video_id = v.video_id).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_playlist_shorts_video_id
  ON playlist_shorts (video_id);
