-- 1. video view change MoM
DROP VIEW IF EXISTS video_stat_change;
create view video_stat_change as
select
    c.category_id,
    cur.report_period,
    v.published_at_period as published_period,
    v.channel_id,
    cur.video_id,
    case when cur.report_period=v.published_at_period then 1 else 0 end as is_new,
    case when v.is_short then 1 else 0 end as is_short,
    v.duration,
    cur.id as cur_vs_id,
    prev.id as prev_vs_id,
    (case
        when prev.video_id is not null then cur.view_count - prev.view_count
        when cur.report_period=v.published_at_period then cur.view_count
        else 0
    end) / (case when is_short then 10 else 1 end) as score,
    case
        when prev.video_id is not null then cur.view_count - prev.view_count
        when cur.report_period=v.published_at_period then cur.view_count
        else 0
    end as view_count,
    case
        when prev.video_id is not null then cur.like_count - prev.like_count
        when cur.report_period=v.published_at_period then cur.like_count
        else 0
    end as like_count,
    case
        when prev.video_id is not null then cur.comment_count - prev.comment_count
        when cur.report_period=v.published_at_period then cur.comment_count
        else 0
    end as comment_count,
    cur.view_count as cur_view_count,
    prev.view_count as prev_view_count,
    cur.like_count as cur_like_count,
    prev.like_count as prev_like_count,
    cur.comment_count as cur_comment_count,
    prev.comment_count as prev_comment_count
from video_stat as cur
left join video as v on v.video_id = cur.video_id
left join video_stat as prev on
        prev.report_period = cur.prev_period
        and prev.video_id=cur.video_id
left join channel as c on c.channel_id = v.channel_id
where v.channel_id is not null
    and c.status>0
order by 1, 2, 3;



-- 2. Sum video views for channels
DROP VIEW IF EXISTS  video_stat_subgroup;
create view video_stat_subgroup as
select
    vs.category_id,
    vs.report_period,
    vs.channel_id,
    vs.published_period,
    vs.is_new,
    vs.is_short,
    count(*) as videos,
    sum(duration) as duration,
    sum(score) as score,
    sum(view_count) as view_count,
    sum(like_count) as like_count,
    sum(comment_count) as comment_count
from video_stat_change as vs
group by 1,2, 3, 4, 5, 6;


-- 3. Prepare data for report by channel, rank channels
DROP VIEW IF EXISTS channel_period_top;
create view channel_period_top as
WITH total_metrics AS (
select
    vs.category_id,
    vs.report_period,
    vs.channel_id,
    sum(score) as score,
    sum(videos*is_new) as videos,
    sum(is_short*is_new) as shorts,
    sum(duration*is_new) as duration,
    sum(view_count) as view_count,
    sum(like_count) as like_count,
    sum(comment_count) as comment_count,
    sum(score * is_short) as score_shorts,
    sum(score * is_new) as score_new,
    sum(score * (1 - is_new)) as score_old
from video_stat_subgroup as vs
group by 1,2, 3),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY report_period, category_id ORDER BY score DESC) AS rank
    FROM total_metrics
)
SELECT *
FROM ranked;


-- 4. Add channel rank change to report
DROP VIEW IF EXISTS channel_period_top_change;
create view channel_period_top_change as
select
    cur.*,
    case when prev.channel_id is null then 0
        else (cur.score - prev.score)
    end as score_change,
    case when prev.channel_id is null then 0
        else -(cur.rank - prev.rank)
    end as rank_change
from channel_period_top as cur
left join channel_period_top prev on
    prev.channel_id = cur.channel_id
        and prev.report_period = (cur.report_period - INTERVAL '1 month');


-- 5. Top videos for each channel
DROP VIEW IF EXISTS channel_period_top_videos;
create view channel_period_top_videos as
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY report_period, channel_id ORDER BY score DESC) AS rank
    FROM video_stat_change
    where is_new=1
)
SELECT
    r.*,
    v.title,
    v.video_url,
    v.thumbnail_url,
    v.is_clickbait,
    v.clickbait_comment
FROM ranked as r
left join video as v on v.video_id = r.video_id;

-- 5. Stat changes on channel level
DROP VIEW IF EXISTS channel_stat_change;
create view channel_stat_change as
select
    cur.report_period,
    c.channel_id,
    c.channel_title,
    cur.channel_view_count,
    cur.video_count,
    cur.subscriber_count,
    case when pr.id is null then null else (cur.channel_view_count - pr.channel_view_count) end as view_change,
    case when pr.id is null then null else (cur.video_count - pr.video_count) end as video_change,
    case when pr.id is null then null else (cur.subscriber_count - pr.subscriber_count) end as subscriber_change
from channel as c
left join channel_stat as cur on cur.channel_id = c.channel_id
left join channel_stat as pr on pr.channel_id = c.channel_id and pr.report_period = (cur.report_period - INTERVAL '1 month')
where c.status > 0
order by 1;


-- 6. Final report view
DROP VIEW IF EXISTS report_view;
create view report_view as
select
    c.*,
    ch.channel_title,
    ch.thumbnail_url,
    ch.custom_url,
    ch.description,
    cs.subscriber_count,
    cs.subscriber_change,
    cs.video_change,
    cs.view_change
from channel_period_top_change as c
left join channel_stat_change cs on c.channel_id = cs.channel_id and c.report_period = cs.report_period
left join channel as ch on ch.channel_id = c.channel_id
order by report_period, category_id, rank;

