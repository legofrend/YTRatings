#!/usr/bin/env node
/** SSG: one HTML per category (latest period). */
import { copyFileSync, existsSync, readFileSync } from 'node:fs'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const env = { ...process.env, NUXT_SSG: '1' }
delete env.SSG_PERIOD
delete env.SSG_ONLY_LATEST

function copySeoIntoOutput() {
  const out = path.join(root, '.output', 'public')
  if (!existsSync(out)) return
  for (const name of ['sitemap.xml', 'robots.txt']) {
    const src = path.join(root, 'public', name)
    if (!existsSync(src)) continue
    copyFileSync(src, path.join(out, name))
    console.log(`[ssg] copied ${name} → .output/public/`)
  }

  // nginx error_page 404 /404.html — flatten Nuxt's /404/index.html
  const nested404 = path.join(out, '404', 'index.html')
  const flat404 = path.join(out, '404.html')
  if (existsSync(nested404)) {
    copyFileSync(nested404, flat404)
    console.log('[ssg] copied 404/index.html → 404.html (nginx)')
  } else if (!existsSync(flat404)) {
    console.warn('[ssg] warn: no 404.html produced — check prerender /404')
  }
  if (existsSync(flat404)) {
    const html = readFileSync(flat404, 'utf8')
    if (!html.includes('не найдена') && !html.includes('выберите категорию')) {
      console.warn(
        '[ssg] warn: 404.html looks empty/wrong — expected NotFoundShell content'
      )
    }
  }
}

console.log(
  `[ssg] generate latest per category from ${env.NUXT_API_BASE || 'NUXT_API_BASE / default'}`
)
const child = spawn('npx', ['nuxt', 'generate'], {
  cwd: root,
  stdio: 'inherit',
  shell: true,
  env,
})
child.on('exit', (code) => {
  if (code === 0) copySeoIntoOutput()
  process.exit(code ?? 1)
})
