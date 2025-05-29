-- step 1: update video_stat: calculate video count change MoM
with updates AS (
select
    cur.id,
    v.channel_id,
    (cur.report_period = v.published_at_period) AS is_new,
    v.is_short,
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
    end as comment_count
from video_stat as cur
left join video as v on v.video_id = cur.video_id
left join video_stat as prev on
        prev.report_period = (cur.report_period - '1 mon'::interval)  -- cur.prev_period
        and prev.video_id=cur.video_id
)
UPDATE video_stat AS vs
SET
    channel_id = u.channel_id,
    is_short = u.is_short,
    is_new = u.is_new,
    period_view_count = u.view_count,
    period_like_count = u.like_count,
    period_comment_count = u.comment_count
FROM updates u
WHERE vs.id = u.id
    and (vs.period_view_count IS NULL
       OR vs.period_like_count IS NULL
       OR vs.period_comment_count IS NULL
       OR vs.is_short IS NULL
       OR vs.is_new IS NULL
       OR vs.channel_id IS NULL
        )
;

-- 2. Update video rank по первому доступному периоду
WITH first_stats AS (
    SELECT DISTINCT ON (vs.video_id)
        vs.video_id,
        vs.report_period,
        vs.view_count
    FROM video_stat vs
    WHERE vs.view_count IS NOT NULL
    ORDER BY vs.video_id, vs.report_period  -- earliest period first
),
ranked AS (
    SELECT
        v.video_id,
        RANK() OVER (
            PARTITION BY v.channel_id, fs.report_period
            ORDER BY v.is_short ASC, COALESCE(fs.view_count, 0)  DESC
        ) AS computed_rank
    FROM video v
    JOIN first_stats fs ON fs.video_id = v.video_id
)
UPDATE video v
SET rank = r.computed_rank
FROM ranked r
WHERE v.video_id = r.video_id
  AND v.rank IS NULL;

-- step 3: update channel_stat: calculate channel count change MoM
with updates AS (
select
    cur.id,
    prev.id as ppcs_id,
    cur.channel_id,
    cur.channel_view_count - coalesce(prev.channel_view_count, 0) view_count,
    cur.subscriber_count - coalesce(prev.subscriber_count, 0) subscriber_count,
    cur.video_count - coalesce(prev.video_count, 0) video_count
from channel_stat as cur
left join channel_stat as prev on
        prev.report_period = (cur.report_period - '1 mon'::interval)
        and prev.channel_id=cur.channel_id
)
UPDATE channel_stat AS cs
SET
    ppcs_id = u.ppcs_id,
    pc_view = u.view_count,
    pc_subscriber = u.subscriber_count,
    pc_video = u.video_count
FROM updates u
WHERE cs.id = u.id
    and (cs.ppcs_id IS NULL
        OR cs.pc_view IS NULL
       OR cs.pc_subscriber IS NULL
--        OR cs.pc_video IS NULL
        )
;

UPDATE channel_stat AS cs
SET    ppcs_id = 0 where ppcs_id is null;

-- step 4: update channel_stat: calculate stat based on video
with channel_periods as
(
SELECT DISTINCT channel_id, report_period
FROM channel_stat
),
video_stats as
(select
--     c.category_id,
    c.channel_id,
    c.report_period,
    sum(case when is_new then 1 else 0 end) as  pv_video,
    sum(case when is_new and is_short is FALSE then 1 else 0 end) as  pv_video_long,
    sum(case when is_new and is_short then 1 else 0 end) as  pv_video_short,
    COALESCE(sum(period_view_count), 0) as  pv_view,
    sum(case when is_new and is_short is FALSE then period_view_count else 0 end) as  pv_view_new_long,
    sum(case when is_new and is_short then period_view_count else 0 end) as  pv_view_new_short,
    sum(case when is_new is FALSE and is_short is FALSE then period_view_count else 0 end) as  pv_view_old_long,
    sum(case when is_new is FALSE and is_short then period_view_count else 0 end) as  pv_view_old_short,
    sum((case when is_short then period_view_count/10 when is_short is False then period_view_count else NULL end)) as  pv_score,
    COALESCE(sum(period_like_count), 0) as  pv_like,
    COALESCE(sum(period_comment_count), 0) as  pv_comment
from channel_periods as c
left join video_stat as vs on vs.channel_id = c.channel_id
group by 1,2
),
ranked as
(
select
    vs.*,
    RANK() OVER (
        PARTITION BY c.category_id, report_period
        ORDER BY COALESCE(pv_score, 0)  DESC
    ) AS pv_score_rank
from video_stats as vs
left join channel as c on c.channel_id=vs.channel_id
where c.status=1
),
duration as
(select
     channel_id,
     published_at_period as report_period,
     sum(duration) as pv_duration
 from video
 group by 1,2
 ),
updates as (
select
    r.*,
    d.pv_duration
from ranked as r
left join duration as d on r.channel_id=d.channel_id and r.report_period=d.report_period
)
UPDATE channel_stat AS cs
SET
    pv_video_long = u.pv_video_long,
    pv_video_short = u.pv_video_short,
    pv_score = u.pv_score,
    pv_view = u.pv_view,
    pv_view_new_long = u.pv_view_new_long,
    pv_view_new_short = u.pv_view_new_short,
    pv_view_old_long = u.pv_view_old_long,
    pv_view_old_short = u.pv_view_old_short,
    pv_like = u.pv_like,
    pv_comment = u.pv_comment,
    pv_duration = u.pv_duration,
    pv_score_rank = u.pv_score_rank
FROM updates as u
WHERE cs.channel_id = u.channel_id and cs.report_period=u.report_period
    and cs.pv_view IS NULL
;

-- step 5: update channel_stat: calculate rank and score change MoM
with updates AS (
select
    cur.id,
    prev.id as ppcs_id,
    cur.channel_id,
    coalesce(cur.pv_score - prev.pv_score, 0) pv_score_change,
    coalesce(cur.pv_score_rank - prev.pv_score_rank, 0) pv_score_rank_change
from channel_stat as cur
left join channel_stat as prev on cur.ppcs_id=prev.id
        or (prev.report_period = (cur.report_period - '1 mon'::interval)
            and prev.channel_id=cur.channel_id)
)
UPDATE channel_stat AS cs
SET
    pv_score_change = u.pv_score_change,
    pv_score_rank_change = u.pv_score_rank_change
FROM updates u
WHERE cs.id = u.id and cs.ppcs_id>0
--     and (cs.pv_score_change IS NULL
--         OR cs.pv_score_rank_change IS NULL
        )
;

-- step 6: update channel: priority
with updates AS (
select
    cs.channel_id,
    case
        when min(pv_score_rank)<=20 then 20
        when min(pv_score_rank)<=100 then 100
        else 1000
    end as priority
from channel_stat as cs
where cs.report_period>='2025-01-01'
group by 1
)
UPDATE channel AS c
SET
    priority = u.priority
FROM updates u
WHERE c.channel_id = u.channel_id
;


-- ppcs_id
-- pv_score_rank_change
-- pv_score_change



-- 1. video view change MoM
create or replace view video_stat_change as
select
    c.category_id,
    cur.report_period,
    v.published_at_period as published_period,
    v.channel_id,
    cur.video_id,
    case when v.is_clickbait=True then 1 else 0 end as is_clickbait,
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
create or replace view video_stat_subgroup as
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
    sum(comment_count) as comment_count,
    sum(is_clickbait) as clickbait_count
from video_stat_change as vs
group by 1, 2, 3, 4, 5, 6
having count(*)>0;


-- 3. Prepare data for report by channel, rank channels
create or replace view channel_period_top as
WITH total_metrics AS (
select
    vs.category_id,
    vs.report_period,
    vs.channel_id,
    sum(score) as score,
    sum(videos*is_new*(1-is_short)) as videos,
    sum(clickbait_count*is_new*(1-is_short)) as video_clickbaits,
    sum(videos*is_new*is_short) as shorts,
    sum(duration*is_new) as duration,
    sum(view_count) as view_count,
    sum(like_count) as like_count,
    sum(comment_count) as comment_count,
    sum(view_count * is_new*(1-is_short)) as view_count_new_video,
    sum(view_count * is_new*is_short) as view_count_new_short,
    sum(view_count * (1 - is_new)*(1-is_short)) as view_count_old_video,
    sum(view_count * (1 - is_new)*is_short) as view_count_old_short
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
create or replace view channel_period_top_change as
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
    case when pr.id is null then null else (cur.channel_view_count - pr.channel_view_count) end as total_view_count_change,
    case when pr.id is null then null else (cur.video_count - pr.video_count) end as total_video_change,
    case when pr.id is null then null else (cur.subscriber_count - pr.subscriber_count) end as subscriber_count_change
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
    cs.subscriber_count_change,
    cs.total_video_change,
    cs.total_view_count_change,
    cs.total_view_count_change - c.view_count as view_count_check
from channel as ch
left join channel_stat_change cs on ch.channel_id = cs.channel_id
left join channel_period_top_change as c on ch.channel_id = c.channel_id and c.report_period = cs.report_period
order by report_period, category_id, rank;


-- 7. Top videos for each channel
create or replace view channel_period_top_videos as
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY report_period, channel_id ORDER BY is_short, score DESC) AS rank
    FROM video_stat_change
    where is_new=1
)
SELECT
    r.*,
    v.title,
    v.video_url,
    v.thumbnail_url,
--     v.is_clickbait,
    v.clickbait_comment
FROM ranked as r
left join video as v on v.video_id = r.video_id;


-- Channel view with category
DROP VIEW IF EXISTS channel_v;
create or replace view channel_v as
select ch.*,
       c.status as category_status,
       c.sys_name,
       c.name as category_name,
       c.title as category_title,
       c.description as category_description
from channel as ch
left join category c on c.id = ch.category_id;

-- Video view with category and channel
DROP VIEW IF EXISTS video_v;
create or replace view video_v as
select v.*,
       channel.*
from video as v
left join channel_v as channel on channel.channel_id=v.channel_id
-- left join category c on c.id = ch.category_id;


-- Reports


-- Report about channels by categories
select ct.id, ct.name,
       count(c.channel_id) as channels,
       sum(case when c.published_at IS NULL then 1 else 0 end) as no_published_date,
       sum(case when c.last_video_fetch_dt is null or c.last_video_fetch_dt<'2025-04-30' then 1 else 0 end) as not_updated,
       sum(case when cs.id is null  then 1 else 0 end) as no_stat,
       max(case when r.id is null  then 1 else 0 end) as no_report
from channel as c
left join category as ct on c.category_id = ct.id
left join channel_stat cs on c.channel_id = cs.channel_id and cs.report_period='2025-04-01'
left join report as r on c.category_id = r.category_id and  r.report_period='2025-04-01'
where c.status= 1 and c.category_id>0 and ct.active=1
group by 1, 2
order by 4 desc ;


-- report about videos by categories
select
    c.id,
    c.name,
    count(distinct v.channel_id) as channels,
    count(*) as videos,
    sum(case when v.duration is null then 1 else 0 end) as duration_null,
    sum(case when v.is_short is null then 1 else 0 end) as is_short_null,
    sum(case when v.published_at_period='2025-04-01'  then 1 else 0 end) as videos_cur_period,
    sum(case when v.published_at_period='2025-04-01' and vs.id is null then 1 else 0 end) as no_stat_cur_period

from video as v
left join channel as ch on ch.channel_id=v.channel_id
left join category c on ch.category_id = c.id
left join video_stat vs on v.video_id = vs.video_id and vs.report_period='2025-04-01'
where v.status=1 and ch.status=1 and c.active=1
group by 1, 2
order by 5 desc, 6 desc, 8 desc;
