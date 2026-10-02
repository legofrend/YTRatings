-- Apply video.is_short from playlist_shorts (UUSH mirror). No YouTube API.
-- Default window per channel: MIN(playlist_shorts.published_at) .. channel.last_shorts_fetch_dt
-- Scope: optional category_id / channel_id; omit → all channels with last_shorts_fetch_dt.

-- 1) short
UPDATE video v
SET is_short = TRUE,
    updated_at = CURRENT_TIMESTAMP
FROM playlist_shorts ps
JOIN channel c ON c.channel_id = ps.channel_id
WHERE v.video_id = ps.video_id
  AND c.last_shorts_fetch_dt IS NOT NULL
  AND ps.published_at < c.last_shorts_fetch_dt
  AND v.is_short IS NULL;
  -- AND c.channel_id = 'UC…'
  -- AND c.category_id = 1

-- 2) not short (only inside synced window; skip channels with empty playlist_shorts)
UPDATE video v
SET is_short = FALSE,
    updated_at = CURRENT_TIMESTAMP
FROM channel c
JOIN (
    SELECT channel_id, MIN(published_at) AS win_from
    FROM playlist_shorts
    GROUP BY channel_id
) w ON w.channel_id = c.channel_id
WHERE v.channel_id = c.channel_id
  AND c.last_shorts_fetch_dt IS NOT NULL
  AND v.published_at >= w.win_from
  AND v.published_at < c.last_shorts_fetch_dt
  AND v.status = 1
  AND v.is_short IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM playlist_shorts ps WHERE ps.video_id = v.video_id
  );
  -- AND c.channel_id = 'UC…'
  -- AND c.category_id = 1

-- 3) orphans: in playlist_shorts but missing from video
SELECT ps.video_id, ps.channel_id, ps.title, ps.published_at
FROM playlist_shorts ps
JOIN channel c ON c.channel_id = ps.channel_id
LEFT JOIN video v ON v.video_id = ps.video_id
WHERE v.video_id IS NULL
  AND c.last_shorts_fetch_dt IS NOT NULL
  AND ps.published_at < c.last_shorts_fetch_dt
ORDER BY ps.published_at DESC;
