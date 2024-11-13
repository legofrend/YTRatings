-- Altering and update tables
alter table video drop column is_short;
alter table category add active boolean default True not null;
alter table channel  add last_video_fetch_dt timestamp default Null;

-- ! remove all data in the table
TRUNCATE TABLE report RESTART IDENTITY;

-- reset id key
SELECT pg_get_serial_sequence('video_stat', 'id');
SELECT setval('category_id_seq', (SELECT MAX(id) FROM category) + 1);

-- set published period for videos
update video set published_at_period = date_trunc('month', published_at)::date where published_at_period is null;

-- update duration and video urls
update video set is_short = case when duration > 65 then 0 else null end
where video.is_short > -1;

update video set
 video_url =
     case
         when is_short and  video_url not like '%short%' then ('https://www.youtube.com/shorts/' || video_id)
         when (not is_short) and  video_url like '%short%' then ('https://www.youtube.com/watch?v=' || video_id)
     end
where (is_short = True and  video_url not like '%short%')
   or (is_short = False and  video_url like '%short%');

-- activate channels depending on subcribers
UPDATE channel
SET status = 0
WHERE channel_id IN (
    SELECT c.channel_id
    FROM channel AS c
    LEFT JOIN channel_stat cs ON c.channel_id = cs.channel_id
    WHERE c.category_id = 7 AND cs.subscriber_count < 1000 and c.status is null
);

update channel set status = null where category_id=7

update channel set last_video_fetch_dt = '2024-11-01'::date where last_video_fetch_dt is null and status > 0;

-------------------------------------------------------------

update video set is_short = True where duration<60 and is_short is FALSE and id>25000

select * from channel_period_top_videos limit 3;

select * from report where category_id = 6 and report_period='2024-10-01';

select * from report_view where category_id = 5 and report_period='2024-10-01'
-- and channel_id = 'UCFkngbKHD8Qd9XxGrgpF59Q'


-- info about channel merged with stat and info about videos in the period
select
    c.id,
    c.channel_id,
    c.custom_url,
    c.channel_title,
    c.description,
    cs.report_period,
    cs.subscriber_count,
    cs.video_count,
    cs.channel_view_count,
    cs.id,
    count(v.video_id) as videos,
    count(vs.id) as video_stats
from channel as c
left join channel_stat cs on c.channel_id = cs.channel_id
left join video v on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id and vs.report_period = cs.report_period
where c.category_id>=0 and c.status = 1
-- and c.id>=390
--     and c.channel_id = 'UC8bw1lINePKw5dBhseYWrdQ'
group by 1,2,3,4,5,6,7,8, 9, 10
-- order by cs.subscriber_count desc ;
order by c.id desc
limit 10;

-- report with category name
select c.id, c.name, r.report_period
from report as r
left join category c on c.id = r.category_id


-- info about videos and their stats per published period
select v.published_at_period,
       count( v.video_id) as videos,
       count(vs.id) as stats
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '2024-10-01'
where c.category_id=1 and v.published_at_period >= '2004-09-01'
group by 1
order by 1
;


-- stat about clickbait feature
select is_clickbait, count(*) from channel_period_top_videos
 where category_id=1 and rank<=3 and is_short=0 and report_period='2024-09-01'
 group by 1;

-- get title for top rank videos where is clickbait is null
select video_id, title from channel_period_top_videos
 where category_id=1 and rank<=3 and is_short=0 and report_period='2024-09-01'
    and is_clickbait is null
 group by 1
 limit 50;



-- Channels in the rank order for the specific period and category
select r.channel_id, r.channel_title
from report_view as r
where report_period = '2024-10-01' and category_id=7;

update channel set status = 0 where channel_id in ()

-- Channels and videos within wo stat
select c.channel_id, c.channel_title,
--        v.video_id,
--        vs.score
       count(*) as videos,
       sum(case  when vs.id is null then 1 else 0 end) as no_stat
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=7
group by 1, 2
;


-- Get videos without stat
select distinct v.video_id
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=3 and vs.id is null
order by c.id;


-- Extract videos for a channel
select v.channel_id, v.published_at_period, v.published_at, v.title, v.duration, v.is_short, v.video_url, vs.report_period,  vs.view_count, vs.like_count, vs.comment_count
from video_stat as vs
left join video v on vs.video_id = v.video_id
where v.channel_id = 'UCWAIvx2yYLK_xTYD4F2mUNw'
order by v.published_at


-- Get channels without videos for the period
select c.id, c.channel_id, c.channel_title
from channel as c
left join video v on v.channel_id = c.channel_id and v.published_at_period = '2024-10-01'
where c.status=1 and c.category_id >= 5 and v.video_id is null
--     and c.channel_id='UCFkngbKHD8Qd9XxGrgpF59Q'
order by 1

