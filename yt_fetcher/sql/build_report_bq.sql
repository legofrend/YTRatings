-- Build nested report JSON inside BigQuery (no Python reshape).
-- Shape matches ReportDAO.query_report_view → SChannel.model_dump():
--   [{ channel_*, rank, rank_change, stat:{...}, top_videos:[{..., stat:{...}}] }]
--
-- Params (set by app.report.dao_bq):
--   @report_period DATE
--   @category_ids  ARRAY<INT64>
--   @top_n         INT64   (default 5)
--   @rank_limit    INT64   (default 100)
--
-- Placeholders filled by Python: {project}, {dataset}

MERGE `{project}.{dataset}.report` AS T
USING (
  WITH top_videos AS (
    SELECT
      tv.channel_id,
      tv.report_period,
      tv.category_id,
      ARRAY_AGG(
        STRUCT(
          tv.video_id AS video_id,
          tv.title AS title,
          tv.is_short AS is_short,
          tv.is_clickbait AS is_clickbait,
          tv.clickbait_comment AS clickbait_comment,
          tv.video_url AS video_url,
          tv.thumbnail_url AS thumbnail_url,
          STRUCT(
            tv.duration AS duration,
            CAST(tv.score AS INT64) AS score,
            tv.view_count AS view_count,
            tv.like_count AS like_count,
            tv.comment_count AS comment_count
          ) AS stat
        )
        ORDER BY tv.`rank`
        LIMIT @top_n
      ) AS top_videos
    FROM `{project}.{dataset}.channel_period_top_videos` AS tv
    WHERE tv.report_period = @report_period
      AND tv.category_id IN UNNEST(@category_ids)
      AND tv.`rank` <= @top_n
    GROUP BY 1, 2, 3
  ),
  channels AS (
    SELECT
      rv.report_period,
      rv.category_id,
      STRUCT(
        rv.channel_id AS channel_id,
        rv.channel_title AS channel_title,
        rv.description AS description,
        rv.`rank` AS `rank`,
        rv.rank_change AS rank_change,
        rv.custom_url AS custom_url,
        rv.thumbnail_url AS thumbnail_url,
        STRUCT(
          rv.videos AS videos,
          rv.video_clickbaits AS video_clickbaits,
          rv.shorts AS shorts,
          rv.duration AS duration,
          CAST(rv.score AS INT64) AS score,
          CAST(rv.score_change AS INT64) AS score_change,
          rv.view_count AS view_count,
          rv.view_count_new_video AS view_count_new_video,
          rv.view_count_new_short AS view_count_new_short,
          rv.view_count_old_video AS view_count_old_video,
          rv.view_count_old_short AS view_count_old_short,
          rv.total_view_count_change AS total_view_count_change,
          rv.view_count_check AS view_count_check,
          rv.like_count AS like_count,
          rv.comment_count AS comment_count,
          rv.subscriber_count AS subscriber_count,
          rv.subscriber_count_change AS subscriber_count_change
        ) AS stat,
        COALESCE(
          tv.top_videos,
          ARRAY<STRUCT<
            video_id STRING,
            title STRING,
            is_short INT64,
            is_clickbait INT64,
            clickbait_comment STRING,
            video_url STRING,
            thumbnail_url STRING,
            stat STRUCT<
              duration INT64,
              score INT64,
              view_count INT64,
              like_count INT64,
              comment_count INT64
            >
          >>[]
        ) AS top_videos
      ) AS channel_obj
    FROM `{project}.{dataset}.report_view` AS rv
    LEFT JOIN top_videos AS tv
      ON tv.channel_id = rv.channel_id
     AND tv.report_period = rv.report_period
     AND tv.category_id = rv.category_id
    WHERE rv.report_period = @report_period
      AND rv.category_id IN UNNEST(@category_ids)
      AND rv.`rank` <= @rank_limit
  ),
  built AS (
    SELECT
      report_period,
      category_id,
      TO_JSON(ARRAY_AGG(channel_obj ORDER BY channel_obj.`rank`)) AS data
    FROM channels
    GROUP BY 1, 2
  )
  SELECT
    m.max_id + ROW_NUMBER() OVER (ORDER BY b.category_id) AS id,
    b.report_period,
    b.category_id,
    b.data,
    CURRENT_TIMESTAMP() AS created_at,
    CURRENT_TIMESTAMP() AS updated_at
  FROM built AS b
  CROSS JOIN (
    SELECT COALESCE(MAX(id), 0) AS max_id
    FROM `{project}.{dataset}.report`
  ) AS m
) AS S
ON T.report_period = S.report_period AND T.category_id = S.category_id
WHEN MATCHED THEN UPDATE SET
  data = S.data,
  updated_at = S.updated_at
WHEN NOT MATCHED THEN INSERT (id, report_period, category_id, data, created_at, updated_at)
VALUES (S.id, S.report_period, S.category_id, S.data, S.created_at, S.updated_at);
