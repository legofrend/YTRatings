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
tools/        analysis/, video_gen/, scrape/ — вспомогательное, в основном не в git
media/        generated: channel_logo/, wordstat_img/ — не в git
site/         зеркало Nuxt .output/public для деплоя — не в git
data/         локальные seed/scratch — не в git
```

Правило: код приложений — в `apps/*`, инфраструктура — в `deploy/`, runtime-артефакты (`media/`, `site/`, `data/`) в git не попадают.

### Подсказка по файлам (`apps/api`)

- `app/api/ytapi` — работа с YouTube API
- `app/.../dao`, `models` — работа с БД (ingest → Postgres only)
- `app/bq` — PG → BigQuery warehouse sync (`client` / `create_tables` / `copy_tables` / `sync`)
- `logger`, `config`, `period`, `media_paths` — вспомогательные классы и функции
- `sql/schema.sql` — DDL (tables / views / indexes / triggers)
- `app/main.py` — CLI пайплайна
- `app/fast_api` — API для фронта (`/api/ytr/*`; `/api/ytr/v2/*` → 308 redirect)

### Параметры для `.env`

- `YT_API_KEY=...`
- `LOG_LEVEL=INFO`
- `YTR_MEDIA_ROOT=...` — корень `media/` (на VPS: `/srv/projects/ytratings/media`)
- DB_* / BQ_* — см. `app/config.py` (BQ_* только для WH sync)

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
| git-репо (canonical) | `/srv/projects/ytratings/` |
| compat symlink | `/var/www/o2t4/backend/YTRatings` → canonical |
| backend + compose | `.../apps/api/` (`.env`, `.env-docker`, `.venv` — тут) |
| frontend source | `.../apps/web/` |
| live SSG (nginx root) | `.../site/` |
| generated media | `.../media/channel_logo/`, `.../media/wordstat_img/` |
| nginx конфиг | `/etc/nginx/sites-available/ytr` → `sites-enabled/ytr` |
| копия nginx в репо | `deploy/nginx/ytr.nginx.conf` |
| systemd | `deploy/systemd/ytr-auto.{service,timer}` → `/etc/systemd/system/` |
| auto schedule (UTC) | 11 / 20 / last‑3..1 @ 05:00 harvest; 1st @ 00:01 + 07:01 close |
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
cd /srv/projects/ytratings   # or compat: /var/www/o2t4/backend/YTRatings
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
chmod +x deploy/systemd/run-auto.sh
systemctl daemon-reload && systemctl enable --now ytr-auto.timer
# systemctl list-timers ytr-auto.timer  # проверить следующие срабатывания (UTC)

# 6) после проверки сайта: снести старое
# rm -rf yt_fetcher frontend frontend-nuxt
```

### Не путать с другими проектами на том же VPS

| Путь / конфиг | Проект |
|---------------|--------|
| `/root/oleg/` | endup, slms, telegram-bot *(legacy → `/srv/projects/`)* |
| `/etc/nginx/sites-available/endup` | endup.info |

### Layout `/srv/projects` (без остановки YTR)

Цель: один корень проектов на VPS (зеркало локального `4. Projects`), YTR не обязан жить под `/var/www/o2t4/backend/`.

```
/srv/projects/
  ytratings/              # monorepo (site/, media/, apps/…)
  end-up/
  slms/
  telegram-spygame-bot/
  …                       # плоско, без слоя oleg/
```

`/root/oleg` → symlink на `/srv/projects` (старые nginx-пути `~/oleg/end-up/...` живы).

**Почему можно двигать YTR без stop:** Postgres — named docker volume (`backend_o2t4_postgresdata`), у `ytr_app` нет bind-mount репо. Nginx/systemd продолжают ходить по старому пути через reverse symlink.

На VPS (после `git pull` в текущий checkout):

```bash
# 1) сейчас, zero-risk: mkdir + alias /srv/projects/ytratings → текущий путь; перенос /root/oleg/*
bash deploy/vps-layout.sh prepare

# 2) когда удобно (секунды, docker не трогаем): mv + symlink старого пути
bash deploy/vps-layout.sh cutover

# 3) опционально: nginx/systemd на канонический путь + reload (контейнеры живут)
bash deploy/vps-layout.sh retarget

bash deploy/vps-layout.sh status
```

После `cutover` + `retarget` деплой по умолчанию идёт в `/srv/projects/ytratings` (`deploy/deploy-ytr.*`). Compat symlink на старом пути можно оставить.

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
`media/` на VPS не в git и не затирается деплоем. SSG по умолчанию с `https://ytr.o2t4.ru/api/ytr`.

### Типичный ручной деплой

```bash
cd /srv/projects/ytratings
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
python -m app.main fetch-channel-stats --cats 1
python -m app.main fetch-videos --cats 1
python -m app.main fetch-video-stats --cats 1
python -m app.main denorm --period 2026-08
python -m app.main build-rating --period 2026-08
# --force: перезаписать channel/video stat, не только missing

# edit-channels: category / status / priority. Default dry-run; --apply writes.
# UI: Shift+click channel logo → JSONL row with @handle (UC… only if no handle).
python -m app.main edit-channels --id @somehandle --status 0
python -m app.main edit-channels --file edits.jsonl --apply

# edits.jsonl (one object per line; null = leave field unchanged):
# {"channel_id":"UCxxx…","status":0}
# {"channel_id":"UCyyy…","category_id":19}
# {"id":"@somehandle","category_id":3,"status":1,"priority":50}
#
# edits.csv:
# channel_id,category_id,status,priority
# UCxxx…,,0,
# UCyyy…,19,,
# @somehandle,3,1,50
```
