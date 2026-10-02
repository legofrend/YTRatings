-- BigQuery port of sql/views.sql (report view chain).
-- Postgres original kept as-is in views.sql.
--
-- Target: learnyoutubeapi-430619.youtube_stats
-- Run statements in order (views depend on each other).
--
-- Diffs vs Postgres:
--   * fully-qualified `project.dataset.table`
--   * DATE_SUB(..., INTERVAL 1 MONTH) instead of date - INTERVAL
--   * prev_period: COALESCE(stored col, DATE_SUB(...)) — PG had a generated column
--   * no ORDER BY inside views
--   * `rank` backtick-quoted (reserved)
--
-- Steps (same numbering as views.sql):
--   1 video_stat_change
--   2 video_stat_subgroup
--   3 channel_period_top
--   4 channel_period_top_change
--   5 channel_stat_change
--   6 report_view
--   7 channel_period_top_videos
--   + channel_v / video_v (helpers)


-- ============================================================================
-- 1. video view change MoM
-- Per-video period deltas (views/likes/comments) vs previous month,
-- score = delta / 10 for shorts. Base for all report aggregations.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.video_stat_change` AS
SELECT
  c.category_id,
  cur.report_period,
  v.published_at_period AS published_period,
  v.channel_id,
  cur.video_id,
  CASE WHEN v.is_clickbait IS TRUE THEN 1 ELSE 0 END AS is_clickbait,
  CASE WHEN cur.report_period = v.published_at_period THEN 1 ELSE 0 END AS is_new,
  CASE WHEN v.is_short IS TRUE THEN 1 ELSE 0 END AS is_short,
  v.duration,
  cur.id AS cur_vs_id,
  prev.id AS prev_vs_id,
  (
    CASE
      WHEN prev.video_id IS NOT NULL THEN cur.view_count - prev.view_count
      WHEN cur.report_period = v.published_at_period THEN cur.view_count
      ELSE 0
    END
  ) / (CASE WHEN v.is_short IS TRUE THEN 10 ELSE 1 END) AS score,
  CASE
    WHEN prev.video_id IS NOT NULL THEN cur.view_count - prev.view_count
    WHEN cur.report_period = v.published_at_period THEN cur.view_count
    ELSE 0
  END AS view_count,
  CASE
    WHEN prev.video_id IS NOT NULL THEN cur.like_count - prev.like_count
    WHEN cur.report_period = v.published_at_period THEN cur.like_count
    ELSE 0
  END AS like_count,
  CASE
    WHEN prev.video_id IS NOT NULL THEN cur.comment_count - prev.comment_count
    WHEN cur.report_period = v.published_at_period THEN cur.comment_count
    ELSE 0
  END AS comment_count,
  cur.view_count AS cur_view_count,
  prev.view_count AS prev_view_count,
  cur.like_count AS cur_like_count,
  prev.like_count AS prev_like_count,
  cur.comment_count AS cur_comment_count,
  prev.comment_count AS prev_comment_count
FROM `learnyoutubeapi-430619.youtube_stats.video_stat` AS cur
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.video` AS v
  ON v.video_id = cur.video_id
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.video_stat` AS prev
  ON prev.report_period = COALESCE(
       cur.prev_period,
       DATE_SUB(cur.report_period, INTERVAL 1 MONTH)
     )
 AND prev.video_id = cur.video_id
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel` AS c
  ON c.channel_id = v.channel_id
WHERE v.channel_id IS NOT NULL
  AND c.status > 0;


-- ============================================================================
-- 2. Sum video views for channels
-- Aggregate video_stat_change by channel × period × published_period × is_new × is_short.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.video_stat_subgroup` AS
SELECT
  vs.category_id,
  vs.report_period,
  vs.channel_id,
  vs.published_period,
  vs.is_new,
  vs.is_short,
  COUNT(*) AS videos,
  SUM(vs.duration) AS duration,
  SUM(vs.score) AS score,
  SUM(vs.view_count) AS view_count,
  SUM(vs.like_count) AS like_count,
  SUM(vs.comment_count) AS comment_count,
  SUM(vs.is_clickbait) AS clickbait_count
FROM `learnyoutubeapi-430619.youtube_stats.video_stat_change` AS vs
GROUP BY 1, 2, 3, 4, 5, 6
HAVING COUNT(*) > 0;


-- ============================================================================
-- 3. Prepare data for report by channel, rank channels
-- Channel metrics per category×period + ROW_NUMBER rank by score.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.channel_period_top` AS
WITH total_metrics AS (
  SELECT
    vs.category_id,
    vs.report_period,
    vs.channel_id,
    SUM(vs.score) AS score,
    SUM(vs.videos * vs.is_new * (1 - vs.is_short)) AS videos,
    SUM(vs.clickbait_count * vs.is_new * (1 - vs.is_short)) AS video_clickbaits,
    SUM(vs.videos * vs.is_new * vs.is_short) AS shorts,
    SUM(vs.duration * vs.is_new) AS duration,
    SUM(vs.view_count) AS view_count,
    SUM(vs.like_count) AS like_count,
    SUM(vs.comment_count) AS comment_count,
    SUM(vs.view_count * vs.is_new * (1 - vs.is_short)) AS view_count_new_video,
    SUM(vs.view_count * vs.is_new * vs.is_short) AS view_count_new_short,
    SUM(vs.view_count * (1 - vs.is_new) * (1 - vs.is_short)) AS view_count_old_video,
    SUM(vs.view_count * (1 - vs.is_new) * vs.is_short) AS view_count_old_short
  FROM `learnyoutubeapi-430619.youtube_stats.video_stat_subgroup` AS vs
  GROUP BY 1, 2, 3
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY report_period, category_id
      ORDER BY score DESC
    ) AS `rank`
  FROM total_metrics
)
SELECT * FROM ranked;


-- ============================================================================
-- 4. Add channel rank change to report
-- MoM score_change and rank_change vs previous period.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.channel_period_top_change` AS
SELECT
  cur.*,
  CASE
    WHEN prev.channel_id IS NULL THEN 0
    ELSE cur.score - prev.score
  END AS score_change,
  CASE
    WHEN prev.channel_id IS NULL THEN 0
    ELSE -(cur.`rank` - prev.`rank`)
  END AS rank_change
FROM `learnyoutubeapi-430619.youtube_stats.channel_period_top` AS cur
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_period_top` AS prev
  ON prev.channel_id = cur.channel_id
 AND prev.report_period = DATE_SUB(cur.report_period, INTERVAL 1 MONTH);


-- ============================================================================
-- 5. Stat changes on channel level
-- MoM channel_stat: subscribers / total views / video count deltas.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.channel_stat_change` AS
SELECT
  cur.report_period,
  c.channel_id,
  c.channel_title,
  cur.channel_view_count,
  cur.video_count,
  cur.subscriber_count,
  CASE
    WHEN pr.id IS NULL THEN NULL
    ELSE cur.channel_view_count - pr.channel_view_count
  END AS total_view_count_change,
  CASE
    WHEN pr.id IS NULL THEN NULL
    ELSE cur.video_count - pr.video_count
  END AS total_video_change,
  CASE
    WHEN pr.id IS NULL THEN NULL
    ELSE cur.subscriber_count - pr.subscriber_count
  END AS subscriber_count_change
FROM `learnyoutubeapi-430619.youtube_stats.channel` AS c
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_stat` AS cur
  ON cur.channel_id = c.channel_id
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_stat` AS pr
  ON pr.channel_id = c.channel_id
 AND pr.report_period = DATE_SUB(cur.report_period, INTERVAL 1 MONTH)
WHERE c.status > 0;


-- ============================================================================
-- 6. Final report view
-- Join ranking + channel meta + channel_stat MoM. Source for ReportDAO.build.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.report_view` AS
SELECT
  c.*,
  ch.channel_title,
  ch.thumbnail_url,
  ch.custom_url,
  ch.description,
  cs.subscriber_count,
  cs.subscriber_count_change,
  cs.total_video_change,
  cs.total_view_count_change,
  cs.total_view_count_change - c.view_count AS view_count_check
FROM `learnyoutubeapi-430619.youtube_stats.channel` AS ch
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_stat_change` AS cs
  ON ch.channel_id = cs.channel_id
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_period_top_change` AS c
  ON ch.channel_id = c.channel_id
 AND c.report_period = cs.report_period;


-- ============================================================================
-- 7. Top videos for each channel
-- New videos in period, ranked by score (long first); titles/urls from video.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.channel_period_top_videos` AS
WITH ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY report_period, channel_id
      ORDER BY is_short, score DESC
    ) AS `rank`
  FROM `learnyoutubeapi-430619.youtube_stats.video_stat_change`
  WHERE is_new = 1
)
SELECT
  r.*,
  v.title,
  v.video_url,
  v.thumbnail_url,
  v.clickbait_comment
FROM ranked AS r
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.video` AS v
  ON v.video_id = r.video_id;


-- ============================================================================
-- Channel view with category
-- Helper: channel + category name/title/description.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.channel_v` AS
SELECT
  ch.*,
  -- PG view used c.status; category table has active
  c.active AS category_status,
  c.sys_name,
  c.name AS category_name,
  c.title AS category_title,
  c.description AS category_description
FROM `learnyoutubeapi-430619.youtube_stats.channel` AS ch
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.category` AS c
  ON c.id = ch.category_id;


-- ============================================================================
-- Video view with category and channel
-- Helper: video + channel_v. BQ forbids duplicate names (PG allowed v.*, channel.*);
-- overlapping cols dropped via EXCEPT; keep channel_* / category_* fields.
-- ============================================================================
CREATE OR REPLACE VIEW `learnyoutubeapi-430619.youtube_stats.video_v` AS
SELECT
  v.*,
  ch.* EXCEPT (
    id,
    channel_id,
    description,
    published_at,
    thumbnail_url,
    status,
    created_at,
    updated_at,
    data
  )
FROM `learnyoutubeapi-430619.youtube_stats.video` AS v
LEFT JOIN `learnyoutubeapi-430619.youtube_stats.channel_v` AS ch
  ON ch.channel_id = v.channel_id;
