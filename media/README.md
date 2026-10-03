# media/ (not in git)

Generated / synced runtime assets. Served by nginx aliases (prod, see `deploy/nginx/`) or Vite middleware (`apps/web` dev).

| Path | URL |
|------|-----|
| `channel_logo/*.jpg` | `/channel_logo/...` |
| `wordstat_img/{cat}_{YYYY-MM}.svg` | `/wordstat_img/...` |

Writers: `apps/api/app/media_paths.py`. Env overrides: `YTR_MEDIA_ROOT`, `CHANNEL_LOGO_DIR`, `WORDSTAT_OUT_DIR`.
