-- Altering and update tables
alter table video drop column is_short;
alter table category add active boolean default True not null;

-- ! remove all data in the table
TRUNCATE TABLE report RESTART IDENTITY;

-- reset id key
SELECT pg_get_serial_sequence('video_stat', 'id');
SELECT setval('report_id_seq', (SELECT MAX(id) FROM report) + 1);

-- set published period for videos
update video set published_at_period = date_trunc('month', published_at)::date where published_at_period is null;

-- update duration and video urls
update video set is_short = case when duration > 65 then 0 else null end
where video.is_short > -1;

update video set
 video_url =
     case
         when video.is_short = 1 and  video_url not like '%short%' then ('https://www.youtube.com/shorts/' || video_id)
         when video.is_short = 0 and  video_url like '%short%' then ('https://www.youtube.com/watch?v=' || video_id)
     end
where (video.is_short = 1 and  video_url not like '%short%')
   or (video.is_short = 0 and  video_url like '%short%');

-- activate channels depending on subcribers
UPDATE channel
SET status = 0
WHERE channel_id IN (
    SELECT c.channel_id
    FROM channel AS c
    LEFT JOIN channel_stat cs ON c.channel_id = cs.channel_id
    WHERE c.category_id = 7 AND cs.subscriber_count < 2000
);

update channel set status = null where category_id=7
-------------------------------------------------------------

select * from channel_period_top_videos limit 3;

select * from report where category_id = 5 and report_period='2024-10-01';

select * from report_view where category_id = 5 and report_period='2024-10-01'
and channel_id = 'UCFkngbKHD8Qd9XxGrgpF59Q'


-- info about channel merged with stat
select
    c.channel_id,
    c.channel_title,
       c.description,
       cs.subscriber_count,
       cs.video_count
from channel as c
left join channel_stat cs on c.channel_id = cs.channel_id
where c.category_id=7 and c.status=1
order by cs.subscriber_count desc ;

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
select c.channel_title,
--        v.video_id,
--        vs.score
       count(*) as videos,
       sum(case  when vs.id is null then 1 else 0 end) as no_stat
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=1
group by 1
;


-- Get videos without stat
select distinct v.video_id
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=3 and vs.id is null
order by c.id;


-- Extract videos for a channel
select v.channel_id, v.published_at_period, v.title, v.duration, v.is_short, v.video_url, vs.report_period,  vs.view_count, vs.like_count, vs.comment_count
from video_stat as vs
left join video v on vs.video_id = v.video_id
where v.channel_id = 'UC6cqazSR6CnVMClY0bJI0Lg'


-- Get channels without videos for the period
select c.id, c.channel_id, c.channel_title, count(*), count(case when v.is_short then 1 else 0 end) as shorts
from channel as c
left join video v on v.channel_id = c.channel_id and v.published_at_period = '2024-10-01'
where c.status=1 and c.category_id=5
    and c.channel_id='UCFkngbKHD8Qd9XxGrgpF59Q'
group by 1, 2, 3
-- having count(*) = 1
order by 1


select report_period, published_period, count(*), sum(is_short) as shorts
from video_stat_change where channel_id='UCFkngbKHD8Qd9XxGrgpF59Q'
group by 1,2

select *
from video_stat_subgroup
where channel_id='UCFkngbKHD8Qd9XxGrgpF59Q'


