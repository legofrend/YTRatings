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
| `frontend-nuxt/` | Nuxt SSG — рейтинг |
| `media/` | generated assets (channel logos, wordstat SVG) — **не в git** |
| `site/` | local/VPS mirror of Nuxt `.output/public` — **не в git** |
| `scripts/` | deploy / dev helpers |
| `nginx/` | backup of VPS nginx conf |
| `analysis/` | notebooks (optional) |
| `data/` | local seed/scratch — **не в git** |

### Подсказка по файлам (`yt_fetcher`)

- `app/api/ytapi` — работа с YouTube API
- `app/.../dao`, `models` — работа с БД (Postgres; raw ingest может писать в BigQuery)
- `logger`, `config`, `period`, `media_paths` — вспомогательные классы и функции
- `sql/views*.sql`, `sql/build_report_bq.sql` — views / сборка отчёта
- `app/main.py` — CLI пайплайна
- `app/fast_api` — API для фронта

### Параметры для `.env`

- `YT_API_KEY=...`
- `LOG_LEVEL=INFO`
- `RAW_DB=postgres|bigquery`
- `YTR_MEDIA_ROOT=...` — корень `media/` (на VPS: `/var/www/o2t4/backend/YTRatings/media`)
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
| backend + compose | `.../yt_fetcher/` |
| frontend source | `.../frontend-nuxt/` |
| live SSG (nginx root) | `.../site/` |
| generated media | `.../media/channel_logo/`, `.../media/wordstat_img/` |
| nginx конфиг | `/etc/nginx/sites-available/ytr` → `sites-enabled/ytr` |
| backup nginx в репо | `nginx/ytr.nginx.conf` |
| docker | `ytr_app` (:5001), `o2t4_db` (:5433) из `yt_fetcher/docker-compose.yml` |

### nginx (сайт ytr)

| Host | Что отдаёт |
|------|------------|
| `ytr.o2t4.ru` | `root` → `.../site/` |
| `ytr.o2t4.ru/channel_logo/` | alias → `.../media/channel_logo/` |
| `ytr.o2t4.ru/wordstat_img/` | alias → `.../media/wordstat_img/` |
| `ytr.o2t4.ru/api/ytr/` | proxy → `http://127.0.0.1:5001/api/ytr/` |
| `o2t4.ru` | `/var/www/o2t4/` (лендинг, не Vue app) |

### Миграция media (один раз на VPS)

```bash
cd /var/www/o2t4/backend/YTRatings
mkdir -p media site
# если ещё лежат в старом frontend/dist:
mv frontend/dist/channel_logo media/ 2>/dev/null || true
mv frontend/dist/wordstat_img media/ 2>/dev/null || true
# скопировать nginx/ytr.nginx.conf → /etc/nginx/sites-available/ytr
nginx -t && systemctl reload nginx
```

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

### Деплой с ПК (рекомендуется)

```powershell
# commit (если dirty) + push + Nuxt SSG + VPS docker rebuild + sync site/
.\scripts\deploy-ytr.ps1 -CommitMessage "your message"

# уже закоммичено:
.\scripts\deploy-ytr.ps1 -SkipCommit

# только фронт / только бэк:
.\scripts\deploy-ytr.ps1 -SkipCommit -SkipDocker
.\scripts\deploy-ytr.ps1 -SkipCommit -SkipGenerate -SkipFrontend
```

Git Bash / WSL: `./scripts/deploy-ytr.sh -m "..."`.  
`media/` на VPS не в git и не затирается деплоем. SSG по умолчанию с `https://ytr.o2t4.ru/api/ytr/v2`.

### Типичный ручной деплой

```bash
cd /var/www/o2t4/backend/YTRatings
git fetch && git checkout <branch> && git pull

# API
cd yt_fetcher && docker compose up -d --build

# Frontend SSG: собрать локально, залить .output/public → site/
# media/ не трогать
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

# edit channels (category / status / priority). Default dry-run; --apply writes.
# UI: Shift+click channel logo → JSONL row with @handle (UC… only if no handle).
python -m app.main edit-channels --id @somehandle --status 0
python -m app.main edit-channels --file scripts/channel_edits.example.jsonl
python -m app.main edit-channels --file edits.jsonl --apply
```
