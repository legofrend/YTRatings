# Рейтинг тематических каналов YouTube

Программа строит рейтинг тематических каналов по количеству просмотров за месяц.

## Алгоритм

1. взять список каналов из БД
2. пройтись по каждому каналу и собрать новые видео
3. пройтись по каждому видео за определенный период и загрузить статистику
4. для каждого канала за период сделать расчет ключевой метрики
5. вывести в порядке убывания ключевой метрики

## Структура monorepo

| Папка | Роль |
|-------|------|
| `yt_fetcher/` | monthly pipeline (ingest) + FastAPI + Docker |
| `frontend/` | Vue 3 (Vite) — веб-оболочка рейтинга |

### Подсказка по файлам (`yt_fetcher`)

- `app/api/ytapi` — работа с YouTube API
- `app/.../dao`, `models` — работа с БД (Postgres; raw ingest может писать в BigQuery)
- `logger`, `config`, `period` — вспомогательные классы и функции
- `sql/views*.sql`, `sql/build_report_bq.sql` — views / сборка отчёта
- `app/main.py` — CLI пайплайна
- `app/fast_api` — API для фронта

### Параметры для `.env`

- `YT_API_KEY=...`
- `LOG_LEVEL=INFO`
- `RAW_DB=postgres|bigquery`
- DB_* / BQ_* — см. `app/config.py`

Секреты (пароли, API keys, SA JSON) — только в `.env` / на VPS, **не в git**.

### Подсказка по YouTube API

https://developers.google.com/youtube/v3/docs

Main objects and properties:

- Channel: id, name, descr, subscribers
- Video: channel_id, id, title, descr, published_at, length, thumbnails
- statistics: likes, visits, comments

---

## Карта VPS

Хост: `o2t4.ru` / `ytr.o2t4.ru` (SSH: `root@` + IP из DNS или твой `~/.ssh/config`).

### YTRatings

| Что | Путь |
|-----|------|
| git-репо | `/var/www/o2t4/backend/YTRatings/` |
| backend + compose | `/var/www/o2t4/backend/YTRatings/yt_fetcher/` |
| frontend source (legacy SPA) | `/var/www/o2t4/backend/YTRatings/frontend/` |
| frontend-nuxt (SSG) | `/var/www/o2t4/backend/YTRatings/frontend-nuxt/` |
| frontend live (nginx root) | `/var/www/o2t4/backend/YTRatings/frontend/dist/` |
| nginx конфиг | `/etc/nginx/sites-available/ytr` → `sites-enabled/ytr` |
| backup nginx в репо | `nginx/ytr.nginx.conf` |
| docker | `ytr_app` (:5001), `o2t4_db` (:5433) из `yt_fetcher/docker-compose.yml` |

### nginx (сайт ytr)

| Host | Что отдаёт |
|------|------------|
| `ytr.o2t4.ru` | `root` → `.../frontend/dist/` (Nuxt SSG) |
| `ytr.o2t4.ru/api/ytr/` | proxy → `http://127.0.0.1:5001/api/ytr/` |
| `o2t4.ru` | `/var/www/o2t4/` (лендинг, не Vue app) |

### Не путать с другими проектами на том же VPS

| Путь / конфиг | Проект |
|---------------|--------|
| `/root/oleg/` | endup, slms, telegram-bot |
| `/etc/nginx/sites-available/endup` | endup.info |

### SSH с ПК

```powershell
# один раз (admin PowerShell): ssh-agent Automatic + Start-Service
ssh-add $env:USERPROFILE\.ssh\id_ed25519
ssh root@o2t4.ru
# или Host из ~/.ssh/config
```

### Типичный ручной деплой

```bash
cd /var/www/o2t4/backend/YTRatings
git fetch && git checkout <branch> && git pull

# API
cd yt_fetcher && docker compose up -d --build

# Frontend SSG: собрать локально (нужен API с sys_name), залить .output/public → frontend/dist/
# Не затирать channel_logo/; empty.png и остальной static — да.
# nginx: try_files $uri $uri/ $uri/index.html =404;
```

## Локально: poetry groups (`yt_fetcher`)

```bash
poetry install                  # только API (как в Docker)
poetry install --with ingest    # monthly pipeline + BQ
poetry install --with ingest,dev
```

## Pipeline CLI

```bash
cd yt_fetcher
python -m app.main channel-stat --cats 1
python -m app.main videos --cats 1
python -m app.main video-stat --cats 1
python -m app.main backfill-denorm --period 2026-08
python -m app.main backfill-channel-denorm --period 2026-08
# --force: перезаписать channel/video stat, не только missing
# publish (report JSONB) obsolete — frontend uses v2 channel_stat/video_stat
```
