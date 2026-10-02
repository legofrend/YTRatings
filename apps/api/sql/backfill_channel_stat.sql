-- channel_stat denorm backfill (mirrors ChannelStatDAO.backfill_denorm).
-- views.sql steps 3–5. Uses materialized video_stat denorm cols.
-- FIX vs legacy step 4: join video_stat on report_period too.

-- :period = DATE '2026-08-01'

-- 1) pc_* / ppcs_id
WITH updates AS (
    SELECT
        cur.id,
        prev.id AS ppcs_id,
        cur.channel_view_count - COALESCE(prev.channel_view_count, 0) AS pc_view,
        cur.subscriber_count - COALESCE(prev.subscriber_count, 0) AS pc_subscriber,
        cur.video_count - COALESCE(prev.video_count, 0) AS pc_video
    FROM channel_stat AS cur
    LEFT JOIN channel_stat AS prev
        ON prev.report_period = cur.report_period - INTERVAL '1 month'
       AND prev.channel_id = cur.channel_id
    WHERE cur.report_period = DATE '2026-08-01'
)
UPDATE channel_stat AS cs
SET
    ppcs_id = COALESCE(u.ppcs_id, 0),
    pc_view = u.pc_view,
    pc_subscriber = u.pc_subscriber,
    pc_video = u.pc_video,
    updated_at = CURRENT_TIMESTAMP
FROM updates u
WHERE cs.id = u.id;

-- 2) pv_* from video_stat + duration + rank (see dao for full SQL)

-- 3) pv_score_change / pv_score_rank_change via ppcs_id
