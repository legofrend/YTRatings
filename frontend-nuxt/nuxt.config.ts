import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineNuxtConfig } from 'nuxt/config'

const API_BASE =
  process.env.NUXT_API_BASE || 'http://127.0.0.1:5000/api/ytr/v2'
const SITE_URL = (
  process.env.NUXT_PUBLIC_SITE_URL || 'https://ytr.o2t4.ru'
).replace(/\/$/, '')

const rootDir = dirname(fileURLToPath(import.meta.url))

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json() as Promise<T>
}

/** Same route set as SSG pages → sitemap stays in sync with structure. */
async function collectPrerenderRoutes(): Promise<string[]> {
  const routes = new Set<string>(['/'])

  const categories = await fetchJson<
    Array<{ id: number; name: string; sys_name?: string | null }>
  >(`${API_BASE}/categories`)

  for (const cat of categories) {
    if (cat.id === 0) continue
    const slug = cat.sys_name?.trim()
    if (!slug) {
      console.warn(`[ssg] skip category ${cat.id} (${cat.name}): empty sys_name`)
      continue
    }

    try {
      const res = await fetchJson<{ periods: string[] }>(
        `${API_BASE}/periods?category_id=${cat.id}`
      )
      if (!res.periods?.length) {
        console.warn(`[ssg] skip /${slug}: no periods`)
        continue
      }
    } catch {
      console.warn(`[ssg] skip /${slug}: periods fetch failed`)
      continue
    }

    routes.add(`/${slug}`)
  }

  const list = [...routes].sort((a, b) => a.localeCompare(b))
  console.log(`[ssg] prerender routes: ${list.length} (latest per category)`)
  return list
}

function writeSeoFiles(routes: string[], targets: string[] = [join(rootDir, 'public')]) {
  const today = new Date().toISOString().slice(0, 10)
  const urls = [...new Set(routes)].sort((a, b) => a.localeCompare(b))

  const body = urls
    .map((path) => {
      const loc = path === '/' ? `${SITE_URL}/` : `${SITE_URL}${path}`
      const priority = path === '/' ? '1.0' : '0.8'
      return `  <url>
    <loc>${escapeXml(loc)}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>${priority}</priority>
  </url>`
    })
    .join('\n')

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${body}
</urlset>
`

  const robots = `User-agent: *
Allow: /

Sitemap: ${SITE_URL}/sitemap.xml
`

  for (const dir of targets) {
    writeFileSync(join(dir, 'sitemap.xml'), sitemap, 'utf8')
    writeFileSync(join(dir, 'robots.txt'), robots, 'utf8')
  }
  console.log(
    `[ssg] wrote sitemap.xml (${urls.length} urls) + robots.txt → ${targets.join(', ')}`
  )
}

function escapeXml(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  ssr: true,

  modules: ['@nuxtjs/tailwindcss'],

  css: ['~/assets/css/main.css'],

  runtimeConfig: {
    apiBase: API_BASE,
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api/ytr/v2',
      siteUrl: SITE_URL,
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'ru' },
      title: 'Рейтинг YouTube каналов',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        {
          name: 'description',
          content: 'Ежемесячный рейтинг YouTube-каналов по категориям',
        },
      ],
      link: [
        { rel: 'icon', href: '/favicon.ico' },
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        {
          rel: 'preconnect',
          href: 'https://fonts.gstatic.com',
          crossorigin: '',
        },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap',
        },
      ],
      bodyAttrs: { class: 'bg-black text-white' },
      script: [
        {
          innerHTML: `(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return}}k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");ym(57521011,"init",{clickmap:true,trackLinks:true,accurateTrackBounce:true});`,
          type: 'text/javascript',
        },
      ],
      noscript: [
        {
          innerHTML:
            '<div><img src="https://mc.yandex.ru/watch/57521011" style="position:absolute;left:-9999px" alt="" /></div>',
        },
      ],
    },
  },

  nitro: {
    prerender: {
      crawlLinks: false,
      concurrency: 2,
      failOnError: false,
      routes: [],
    },
  },

  hooks: {
    async 'nitro:config'(nitroConfig) {
      if (nitroConfig.dev) return
      const generating =
        process.argv.some((a) => a === 'generate' || a.endsWith('generate')) ||
        process.env.npm_lifecycle_event === 'generate' ||
        process.env.NUXT_SSG === '1'
      if (!generating) return

      const routes = await collectPrerenderRoutes()
      writeSeoFiles(routes)

      nitroConfig.prerender = nitroConfig.prerender || {}
      nitroConfig.prerender.routes = [
        ...new Set([...(nitroConfig.prerender.routes || []), ...routes]),
      ]
    },
  },

  vite: {
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:5000',
          changeOrigin: true,
        },
      },
    },
  },
})
