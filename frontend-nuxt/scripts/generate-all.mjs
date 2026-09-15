#!/usr/bin/env node
/** SSG: one HTML per category (latest period). */
import { copyFileSync, existsSync } from 'node:fs'
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
