alter table video drop column is_short;
alter table category add active boolean default True not null;

TRUNCATE TABLE report RESTART IDENTITY;

SELECT pg_get_serial_sequence('video_stat', 'id');
SELECT setval('video_id_seq', (SELECT MAX(id) FROM video) + 1);


select c.channel_title,
       c.description,
       cs.subscriber_count,
       cs.video_count
from channel as c
left join channel_stat cs on c.channel_id = cs.channel_id
where c.category_id=5
order by cs.subscriber_count desc ;

UPDATE channel
SET status = 1
WHERE channel_id IN (
    SELECT c.channel_id
    FROM channel AS c
    LEFT JOIN channel_stat cs ON c.channel_id = cs.channel_id
    WHERE c.category_id = 5 AND cs.subscriber_count >= 5000
);

select c.id, c.name, r.report_period
from report as r
left join category c on c.id = r.category_id

select
    c.channel_id,
    c.channel_title,
    cs.id
from channel as c
left join channel_stat as cs on c.channel_id = cs.channel_id and cs.data_at >= '2024-09-30'
where c.status>0
order by 3;

select
    c.channel_id
from channel as c;


select channel_id, count(*)
    from video
    where published_at_period='2024-09-01'
group by 1;

select v.published_at_period,
       count( v.video_id),
       count(vs.id)
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '2024-10-01'
where c.category_id=5 and v.published_at_period >= '2024-08-01'
group by 1
;

select distinct v.video_id
from video as v
    left join channel as c on c.channel_id = v.channel_id
    left join video_stat vs on v.video_id = vs.video_id and vs.report_period = '2024-10-01'
where c.category_id=6 and vs.id is null and v.published_at_period >= '2024-09-01';

-- vs.id is null and


select is_clickbait, count(*) from channel_period_top_videos
 where category_id=1 and rank<=3 and is_short=0 and report_period='2024-09-01'
 group by 1;

select video_id, title from channel_period_top_videos
 where category_id=1 and rank<=3 and is_short=0 and report_period='2024-09-01'
    and is_clickbait is null
 group by 1
 limit 50;

update video set published_at_period = date_trunc('month', published_at)::date where published_at_period is null;

select date_trunc('month', published_at)::date from video limit 3;

select * from channel_period_top_videos limit 3;


update video set video_url = ('https://www.youtube.com/shorts/' || video_id)
where video.is_short = 1 and  video_url not like '%short%';

update video set video_url = ('https://www.youtube.com/watch?v=' || video_id)
where video.is_short = 0 and  video_url like '%short%';

update video set is_short = case when duration > 65 then 0 else null end
where video.is_short > -1;


select is_short,
       video_url LIKE '%short%' as url_for_short,
       count(*)
from video group by 1,2;

select is_short, count(*) from video group by 1;

select video_id from video where is_short is null limit 10;

select * from report limit 5;


select r.*
from report_view as r
where report_period = '2024-09-01' and category_id=3;

select c.channel_title,
--        v.video_id,
--        vs.score
       count(*) as videos,
       sum(case  when vs.id is null then 1 else 0 end) as no_stat
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=3
group by 1
order by c.id;



select distinct v.video_id
from video as v
left join channel as c on c.channel_id = v.channel_id
left join video_stat vs on v.video_id = vs.video_id
where c.category_id=3 and vs.id is null
order by c.id;


select r.*, subscriber_count
from report as r
where report_period = '2024-09-01' and category_id = 1;






