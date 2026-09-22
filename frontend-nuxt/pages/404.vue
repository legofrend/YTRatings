<script setup lang="ts">
/**
 * Stationary 404 — prerendered to /404/index.html, copied to /404.html for nginx.
 * Soft-404 for unknown sys_name still lives in pages/[sysName].vue.
 *
 * Do NOT setResponseStatus(404) during prerender — Nitro then emits an empty
 * error shell as 404.html instead of this page's HTML.
 */
useSeoMeta({
  title: '404 — страница не найдена | YTRatings',
  description:
    'Страница не найдена. Выберите категорию рейтинга ютуб-каналов.',
  robots: 'noindex, follow',
})
</script>

<template>
  <NotFoundShell
    :status-code="404"
    status-message="Страница не найдена. Выберите категорию."
  />
</template>
