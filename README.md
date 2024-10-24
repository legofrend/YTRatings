# Рейтинг тематических каналов YouTube

Программа строит рейтинг тематических каналов по количеству просмотров за месяц.

Алгоритм

1. взять список каналов из БД
2. пройтись по каждому каналу и собрать новые видео
3. пройтись по каждому видео за определенный период и загрузить статистику
4. для каждого канала за период сделать расчет ключевой метрики
5. вывести в порядке убывания ключевой метрики

## Подсказка по файлам

- ytapi - работа с API YT
- database, dao, models - работа с БД Sqlite для сохранениния данных
- logger, config, period - вспомогательные классы и функции
- sql/views - views для составления финального отчета
- services - собранные в функции шаги алгоритма
- analysis.ipynb - jupyter notebook для ручного анализа и построения финального отчета

## Параметры для .env

- YT_API_KEY=XXX
- LOG_LEVEL=INFO

## Подсказка по YouTube API

https://developers.google.cn/youtube/v3/docs
Main objects and properties:

- Channel: id, name, descr, subscribers
- Video: channel_id, id, title, descr, published_at, length, thubnails,
- statistics: likes, visits, comments
