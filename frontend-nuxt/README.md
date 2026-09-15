# frontend-nuxt

Hybrid SSG: **одна статическая страница на категорию** (latest period).  
Архив периодов — клиентский fetch к FastAPI.

## URL

- `/` → редирект на `/news_politics` (или первую с `sys_name`)
- `/{sys_name}` — SSG, latest в HTML (SEO)
- `/{sys_name}?period=2026-07-01` — тот же shell, данные с API
- `?limit=10|20|100` — сколько строк показать

Примеры: `/ai`, `/finance`, `/news_politics?period=2026-01-01&limit=50`

## Dev

Локальный FastAPI на `:5000` (с `sys_name` в `/categories`):

```bash
cd frontend-nuxt
npm install
npm run dev          # proxy /api → :5000
```

## SSG

```bash
npm run generate     # ~N HTML = активные категории + sitemap.xml + robots.txt
```

При каждом generate из API категорий пишутся:
- `public/sitemap.xml` → все `/` и `/{sys_name}`
- `public/robots.txt` → `Sitemap: https://ytr.o2t4.ru/sitemap.xml`

Нужен `NUXT_API_BASE` с `sys_name` (локальный API или задеплоенный бэкенд).  
Артефакт: `.output/public/` → nginx. Node на VPS не нужен.

## Прод

- `NUXT_PUBLIC_API_BASE=/api/ytr/v2` (same-origin)
- после месячного ETL: снова `npm run generate` + залить статику
