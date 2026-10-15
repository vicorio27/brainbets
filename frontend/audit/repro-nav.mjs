// Navigate Dashboard <-> other views repeatedly and report failed or slow API requests.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const failures = []
const timings = {}
const started = new Map()
page.on('request', (r) => { if (r.url().includes('/api/')) started.set(r, Date.now()) })
page.on('requestfinished', async (r) => {
  if (!r.url().includes('/api/')) return
  const ms = Date.now() - (started.get(r) || Date.now())
  const path = new URL(r.url()).pathname
  const res = await r.response()
  ;(timings[path] ||= []).push(ms)
  if (res && res.status() >= 400) failures.push(`${res.status()} ${path} (${ms} ms)`)
})
page.on('requestfailed', (r) => {
  if (r.url().includes('/api/')) failures.push(`FALLO ${new URL(r.url()).pathname}: ${r.failure()?.errorText} (${Date.now() - (started.get(r) || Date.now())} ms)`)
})
const texts = []
for (let round = 0; round < 4; round++) {
  for (const route of ['/', '/caja', '/', '/predictions', '/', '/analytics']) {
    await page.click(`nav a[href="${route}"]`).catch(() => page.goto(base + route))
    await page.waitForTimeout(route === '/' ? 1200 : 500)
    const body = await page.locator('body').innerText()
    if (/network error/i.test(body)) texts.push(`ronda ${round} ${route}: aparece "Network Error"`)
  }
}
await page.goto(base + '/', { waitUntil: 'networkidle' })
console.log('errores en pantalla:', texts.length ? texts : 'ninguno')
console.log('peticiones fallidas:', failures.length ? failures : 'ninguna')
for (const [path, list] of Object.entries(timings).sort((a, b) => Math.max(...b[1]) - Math.max(...a[1])).slice(0, 10)) {
  console.log(`  ${path}: ${list.length} veces, max ${Math.max(...list)} ms, mediana ${list.sort((a, b) => a - b)[list.length >> 1]} ms`)
}
await browser.close()
