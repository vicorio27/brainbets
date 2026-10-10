// Smoke check after the edge / Caja-tabs / player-profile changes:
// every touched screen renders without page errors.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const out = process.argv[2] || 'audit/output'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

await page.goto(`${base}/caja`, { waitUntil: 'networkidle' })
await page.waitForTimeout(4000)
for (const name of ['Por mercado', 'Hoy', 'Histórico y simulación', 'Auditoría']) {
  await page.getByRole('tab', { name: new RegExp(name) }).click()
  await page.waitForTimeout(300)
  const h = await page.evaluate(() => document.documentElement.scrollHeight)
  console.log('caja tab', name, '-> height', h)
  await page.screenshot({ path: `${out}/caja-tab-${name.split(' ')[0].toLowerCase()}.png`, fullPage: true })
}
await page.getByRole('tab', { name: /Hoy/ }).click()
await page.getByText('Ver cuánto poner en cada una').click()
console.log('suspicious flags in today table:', await page.getByText(/⚠ modelo/).count())

await page.goto(base, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: /Apuestas/ }).click()
await page.waitForTimeout(800)
console.log('apuestas tab text:', (await page.locator('main, #app').first().innerText()).replace(/\s+/g, ' ').slice(0, 500))
await page.getByRole('button', { name: /Fiabilidad/ }).click()
await page.locator('input[list="reliability-players"]').fill('hurkacz')
await page.waitForTimeout(2500)
const card = page.locator('div', { hasText: 'Rendimiento por superficie (histórico)' }).last()
console.log('profile:', (await card.innerText()).replace(/\s+/g, ' ').slice(-520))
await card.screenshot({ path: `${out}/profile-card.png` })

await page.goto(`${base}/predictions`, { waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
console.log('predictions: edge badges', await page.locator('td span.rounded-full').count(), '| suspicious notes', await page.getByText(/⚠ modelo/).count())
console.log('page errors:', errors)
await browser.close()
