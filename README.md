# Рейтинг тематических каналов YouTube

Программа строит рейтинг тематических каналов по количеству просмотров за месяц.

## Алгоритм

1. взять список каналов из БД
2. пройтись по каждому каналу и собрать новые видео
3. пройтись по каждому видео за определенный период и загрузить статистику
4. для каждого канала за период сделать расчет ключевой метрики
5. вывести в порядке убывания ключевой метрики

## Структура monorepo

```
apps/
  api/        Python: monthly pipeline (ingest) + FastAPI + Docker
  web/        Nuxt SSG — сайт рейтинга
deploy/       всё, что едет на VPS
  deploy-ytr.ps1 / .sh   точка входа деплоя с ПК
  nginx/                 конфиг сайта (копия /etc/nginx/sites-available/ytr)
  systemd/               ytr-auto.service / .timer + run-auto.sh
scripts/      локальная разработка (dev-ytr.ps1 / .sh)
tools/        analysis/ (notebooks), video_gen/ — вспомогательное, в основном не в git
media/        generated: channel_logo/, wordstat_img/ — не в git
site/         зеркало Nuxt .output/public для деплоя — не в git
data/         локальные seed/scratch — не в git
```

Правило: код приложений — в `apps/*`, инфраструктура — в `deploy/`, runtime-артефакты (`media/`, `site/`, `data/`) в git не попадают.

### Подсказка по файлам (`apps/api`)

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
| backend + compose | `.../apps/api/` (`.env`, `.env-docker`, `.venv` — тут) |
| frontend source | `.../apps/web/` |
| live SSG (nginx root) | `.../site/` |
| generated media | `.../media/channel_logo/`, `.../media/wordstat_img/` |
| nginx конфиг | `/etc/nginx/sites-available/ytr` → `sites-enabled/ytr` |
| копия nginx в репо | `deploy/nginx/ytr.nginx.conf` |
| systemd | `deploy/systemd/ytr-auto.{service,timer}` → `/etc/systemd/system/` |
| логи | `.../apps/api/logs/yt_fetcher.log`, `auto-cron.log` |
| docker | `ytr_app` (:5001), `o2t4_db` (:5433) из `apps/api/docker-compose.yml` (compose project `yt_fetcher`) |

### nginx (сайт ytr)

| Host | Что отдаёт |
|------|------------|
| `ytr.o2t4.ru` | `root` → `.../site/` |
| `ytr.o2t4.ru/channel_logo/` | alias → `.../media/channel_logo/` |
| `ytr.o2t4.ru/wordstat_img/` | alias → `.../media/wordstat_img/` |
| `ytr.o2t4.ru/api/ytr/` | proxy → `http://127.0.0.1:5001/api/ytr/` |
| `o2t4.ru` | `/var/www/o2t4/` (лендинг, не Vue app) |

### Миграция на layout `apps/` + `media/` (один раз на VPS)

```bash
cd /var/www/o2t4/backend/YTRatings
git fetch && git checkout refactor/media-and-cleanup && git pull

# 1) секреты и логи API: не в git, git pull их не переносит
for f in .env .env-docker ytr_sa_key.json logs; do
  [ -e yt_fetcher/$f ] && [ ! -e apps/api/$f ] && mv yt_fetcher/$f apps/api/
done

# 2) host venv для auto (venv нельзя переносить — пересоздать)
cd apps/api && python3.12 -m venv .venv \
  && .venv/bin/pip install -r <(poetry export --with ingest --without-hashes) && cd ../..

# 3) media + site
mkdir -p media site
mv frontend/dist/channel_logo media/ 2>/dev/null || true
mv frontend/dist/wordstat_img media/ 2>/dev/null || true

# 4) docker: тот же compose project (name: yt_fetcher) — контейнеры пересоберутся на месте
cd apps/api && docker compose up -d --build && cd ../..

# 5) nginx + systemd
cp deploy/nginx/ytr.nginx.conf /etc/nginx/sites-available/ytr
nginx -t && systemctl reload nginx
cp deploy/systemd/ytr-auto.service deploy/systemd/ytr-auto.timer /etc/systemd/system/
chmod +x deploy/systemd/run-auto.sh && systemctl daemon-reload

# 6) после проверки сайта: снести старое
# rm -rf yt_fetcher frontend frontend-nuxt
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
.\deploy\deploy-ytr.ps1 -CommitMessage "your message"

# уже закоммичено:
.\deploy\deploy-ytr.ps1 -SkipCommit

# только фронт / только бэк:
.\deploy\deploy-ytr.ps1 -SkipCommit -SkipDocker
.\deploy\deploy-ytr.ps1 -SkipCommit -SkipGenerate -SkipFrontend
```

Git Bash / WSL: `./deploy/deploy-ytr.sh -m "..."`.  
Локальный dev (FastAPI :5000 + Nuxt :3000): `.\scripts\dev-ytr.ps1`.  
`media/` на VPS не в git и не затирается деплоем. SSG по умолчанию с `https://ytr.o2t4.ru/api/ytr/v2`.

### Типичный ручной деплой

```bash
cd /var/www/o2t4/backend/YTRatings
git fetch && git checkout <branch> && git pull

# API
cd apps/api && docker compose up -d --build

# Frontend SSG: собрать локально, залить .output/public → site/
# media/ не трогать
```

## Локально: poetry groups (`apps/api`)

```bash
cd apps/api
python -m venv .venv            # poetry подхватит in-project .venv
poetry install                  # только API (как в Docker)
poetry install --with ingest    # monthly pipeline + BQ
poetry install --with ingest,dev
```

## Pipeline CLI

```bash
cd apps/api
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
