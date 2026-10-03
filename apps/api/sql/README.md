# `sql/`

| Файл | Роль |
|------|------|
| `schema.sql` | полный DDL с живой VPS БД (tables, views, indexes, triggers, functions) |
| `migrate_channel_rating.sql` | additive: create `channel_rating` + copy from `channel_stat`⋈`channel` (no drops) |

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/schema.sql
# или: docker exec -i o2t4_db psql -U root -d ytr_db < sql/schema.sql
```

Приложение SQL-файлы не читает в рантайме. API фронта — FastAPI v2.

Таблица `report` (JSONB) остаётся в schema как исторические данные; при желании её можно залить в BQ через `python -m app.bq.copy_tables report` (см. `app/bq/`). Ежемесячный пайплайн и фронт её не используют.

PG → BQ (аналитика / бэкап):

```bash
cd apps/api
poetry run python -m app.bq.sync --period 2026-08
poetry run python -m app.bq.copy_tables          # полный снимок / subset
```
