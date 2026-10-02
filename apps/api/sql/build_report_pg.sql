-- Build nested report JSON in Postgres (same shape as build_report_bq.sql / SChannel).
-- Call per (report_period, category_id) from Python — early filters keep memory down.
--
-- Params:
--   :report_period DATE
--   :category_id   INT
--   :top_n         INT  (default 5)
--   :rank_limit    INT  (default 100)
--
-- Does NOT scan bare report_view; filters channel_period_top_change first.

INSERT INTO report (report_period, category_id, data)
SELECT
    :report_period AS report_period,
    :category_id AS category_id,
    COALESCE(
        jsonb_agg(channel_obj ORDER BY (channel_obj ->> 'rank')::int),
        '[]'::jsonb
    ) AS data
FROM (
    SELECT
        jsonb_build_object(
            'channel_id', c.channel_id,
            'channel_title', ch.channel_title,
            'description', COALESCE(ch.description, ''),
            'rank', c.rank,
            'rank_change', c.rank_change,
            'custom_url', ch.custom_url,
            'thumbnail_url', ch.thumbnail_url,
            'stat', jsonb_build_object(
                'videos', c.videos,
                'video_clickbaits', c.video_clickbaits,
                'shorts', c.shorts,
                'duration', c.duration,
                'score', CAST(ROUND(c.score) AS bigint),
                'score_change', CAST(ROUND(c.score_change) AS bigint),
                'view_count', c.view_count,
                'view_count_new_video', c.view_count_new_video,
                'view_count_new_short', c.view_count_new_short,
                'view_count_old_video', c.view_count_old_video,
                'view_count_old_short', c.view_count_old_short,
                'total_view_count_change', cs.total_view_count_change,
                'view_count_check', cs.total_view_count_change - c.view_count,
                'like_count', c.like_count,
                'comment_count', c.comment_count,
                'subscriber_count', cs.subscriber_count,
                'subscriber_count_change', cs.subscriber_count_change
            ),
            'top_videos', COALESCE(tv.top_videos, '[]'::jsonb)
        ) AS channel_obj
    FROM channel_period_top_change AS c
    JOIN channel AS ch ON ch.channel_id = c.channel_id
    LEFT JOIN channel_stat_change AS cs
        ON cs.channel_id = c.channel_id
       AND cs.report_period = c.report_period
    LEFT JOIN (
        SELECT
            t.channel_id,
            jsonb_agg(
                jsonb_build_object(
                    'video_id', t.video_id,
                    'title', t.title,
                    'is_short', t.is_short,
                    'is_clickbait', t.is_clickbait,
                    'clickbait_comment', t.clickbait_comment,
                    'video_url', t.video_url,
                    'thumbnail_url', t.thumbnail_url,
                    'stat', jsonb_build_object(
                        'duration', t.duration,
                        'score', CAST(ROUND(t.score) AS bigint),
                        'view_count', t.view_count,
                        'like_count', t.like_count,
                        'comment_count', t.comment_count
                    )
                )
                ORDER BY t.rank
            ) AS top_videos
        FROM channel_period_top_videos AS t
        WHERE t.report_period = :report_period
          AND t.category_id = :category_id
          AND t.rank <= :top_n
        GROUP BY t.channel_id
    ) AS tv ON tv.channel_id = c.channel_id
    WHERE c.report_period = :report_period
      AND c.category_id = :category_id
      AND c.rank <= :rank_limit
) AS channels
ON CONFLICT ON CONSTRAINT uq_period_category
DO UPDATE SET
    data = EXCLUDED.data,
    updated_at = CURRENT_TIMESTAMP;
