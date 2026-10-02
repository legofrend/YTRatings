1. распарсить данные по топ каналов категорий с сайтов
   [https://whatstat.ru/youtube/channels?sort=views](https://whatstat.ru/youtube/channels?sort=views)
   [https://livedune.com/ru/ratings/youtube/russia/category/news_politics/?sort=vr](https://livedune.com/ru/ratings/youtube/russia/category/news_politics/?sort=vr)
2. оптимизация back-fill: заполнять максимум сразу и по тригеру, чтобы убрать отдельный шаг
   Чтобы не делать отдельный join «потом», достаточно расширить выборку кандидатов:

get_ids_wo_stat → [(video_id, channel_id, published_at_period), ...]
и перед записью:

item["channel_id"] = meta[vid].channel_id
item["is_new"] = (report_period == meta[vid].published_at_period)

period — либо второй lookup prev video_stat батчем, либо BEFORE INSERT trigger

3. баг close: `last_video_fetch_dt` / `last_shorts_fetch_dt` пишутся через `min(datetime.now(), period_end)`,
   а `datetime.now()` = локаль VPS (**UTC**), тогда как окно сценария и смысл «конец месяца» — **MSK**.
   На запуске 01.10 ~00:01 MSK (= 30.09 21:01 UTC) маркер становится `2026-09-30 …`,
   `period_end` = `2026-10-01 00:00` naive → каналы считаются недозакрытыми и **прогоняются повторно**.
   Fix: единая TZ (MSK или UTC) для `now`, `period_end` и сравнения `last_*_fetch_dt >= period_end`
   (и то же в shorts-sync). После фикса — не жечь квоту на уже закрытых каналах.
4. наладить wordstat, за какой период и когда нужно обновлять

5. ~~перенести картинки лого и статы в отдельную папку media~~ → `media/` + nginx alias + `site/`
