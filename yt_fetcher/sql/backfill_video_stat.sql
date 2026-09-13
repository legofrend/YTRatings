-- Staging (UNLOGGED) + batched UPDATE — mirrors VideoStatDAO.backfill_denorm.
-- Logic matches video_stat_change; joins inlined (no view).

DROP TABLE IF EXISTS _vs_denorm_stg;

CREATE UNLOGGED TABLE _vs_denorm_stg AS
SELECT
    cur.id,
    v.channel_id,
    (cur.report_period = v.published_at_period) AS is_new,
    (CASE WHEN v.is_short THEN TRUE ELSE FALSE END) AS is_short,
    CASE
        WHEN prev.video_id IS NOT NULL THEN cur.view_count - prev.view_count
        WHEN cur.report_period = v.published_at_period THEN cur.view_count
        ELSE 0
    END AS period_view_count,
    CASE
        WHEN prev.video_id IS NOT NULL THEN cur.like_count - prev.like_count
        WHEN cur.report_period = v.published_at_period THEN cur.like_count
        ELSE 0
    END AS period_like_count,
    CASE
        WHEN prev.video_id IS NOT NULL THEN cur.comment_count - prev.comment_count
        WHEN cur.report_period = v.published_at_period THEN cur.comment_count
        ELSE 0
    END AS period_comment_count
FROM video_stat AS cur
JOIN video AS v ON v.video_id = cur.video_id
LEFT JOIN video_stat AS prev
    ON prev.report_period = cur.prev_period
   AND prev.video_id = cur.video_id
JOIN channel AS c ON c.channel_id = v.channel_id
WHERE cur.report_period = DATE '2026-08-01'
  AND v.channel_id IS NOT NULL
  AND c.status > 0
  AND (
      cur.channel_id IS NULL
      OR cur.is_short IS NULL
      OR cur.is_new IS NULL
      OR cur.period_view_count IS NULL
      OR cur.period_like_count IS NULL
      OR cur.period_comment_count IS NULL
  );

CREATE INDEX ON _vs_denorm_stg (id);
-- SELECT count(*) FROM _vs_denorm_stg;

-- Repeat until 0 rows (or let Python loop):
WITH batch AS (
    SELECT id FROM _vs_denorm_stg ORDER BY id LIMIT 10000
),
upd AS (
    UPDATE video_stat AS vs
    SET
        channel_id = s.channel_id,
        is_short = s.is_short,
        is_new = s.is_new,
        period_view_count = s.period_view_count,
        period_like_count = s.period_like_count,
        period_comment_count = s.period_comment_count,
        updated_at = CURRENT_TIMESTAMP
    FROM _vs_denorm_stg AS s
    JOIN batch b ON b.id = s.id
    WHERE vs.id = s.id
    RETURNING s.id
)
DELETE FROM _vs_denorm_stg s
USING upd
WHERE s.id = upd.id;

-- DROP TABLE IF EXISTS _vs_denorm_stg;
