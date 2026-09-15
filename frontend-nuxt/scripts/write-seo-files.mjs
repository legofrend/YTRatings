#!/usr/bin/env node
/**
 * Standalone: rebuild public/sitemap.xml + robots.txt from categories API.
 * Also runs automatically inside `nuxt generate` (nuxt.config hook).
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const API_BASE =
  process.env.NUXT_API_BASE || 'http://127.0.0.1:5000/api/ytr/v2'
const SITE_URL = (
  process.env.NUXT_PUBLIC_SITE_URL || 'https://ytr.o2t4.ru'
).replace(/\/$/, '')
const rootDir = dirname(fileURLToPath(import.meta.url))
const publicDir = join(rootDir, '..', 'public')

async function fetchJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return res.json()
}

function escapeXml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const routes = new Set(['/'])
const categories = await fetchJson(`${API_BASE}/categories`)
for (const cat of categories) {
  if (cat.id === 0) continue
  const slug = cat.sys_name?.trim()
  if (!slug) continue
  try {
    const res = await fetchJson(
      `${API_BASE}/periods?category_id=${cat.id}`
    )
    if (!res.periods?.length) continue
  } catch {
    continue
  }
  routes.add(`/${slug}`)
}

const urls = [...routes].sort((a, b) => a.localeCompare(b))
const today = new Date().toISOString().slice(0, 10)
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

const targets = [publicDir]
const outPublic = join(rootDir, '..', '.output', 'public')
if (existsSync(join(rootDir, '..', '.output'))) {
  mkdirSync(outPublic, { recursive: true })
  targets.push(outPublic)
}

for (const dir of targets) {
  writeFileSync(join(dir, 'sitemap.xml'), sitemap, 'utf8')
  writeFileSync(join(dir, 'robots.txt'), robots, 'utf8')
}
console.log(
  `[seo] sitemap.xml (${urls.length} urls) + robots.txt → ${targets.join(', ')}`
)
