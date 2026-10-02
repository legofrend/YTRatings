# media/ (not in git)

Generated / synced runtime assets. Served by nginx aliases (prod) or Vite middleware (Nuxt dev).

| Path | URL |
|------|-----|
| `channel_logo/*.jpg` | `/channel_logo/...` |
| `wordstat_img/{cat}_{YYYY-MM}.svg` | `/wordstat_img/...` |

Env overrides: `YTR_MEDIA_ROOT`, `CHANNEL_LOGO_DIR`, `WORDSTAT_OUT_DIR`.

On VPS once: move old `frontend/dist/{channel_logo,wordstat_img}` here, then deploy `site/` + updated nginx.
