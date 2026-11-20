-- Duplicate of UNIQUE constraint playlist_shorts_video_id_key (btree on video_id).
-- apply-is-short JOIN and upserts use the UNIQUE index.
DROP INDEX CONCURRENTLY IF EXISTS idx_playlist_shorts_video_id;
