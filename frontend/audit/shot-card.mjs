// The full (not finished) match card: forces today's tennis matches to SCHEDULED on the API response.
import { chromium } from 'playwright'
const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/api/v1/matches/**', async (route) => {
    const res = await route.fetch()
    let body = await res.text()
    try {
      const j = JSON.parse(body)
      for (const m of j.tennis || []) { m.status = 'SCHEDULED'; m.setScores = null; m.finalSets = null; m.winner = null }
      body = JSON.stringify(j)
    } catch (e) { /* not the list */ }
    await route.fulfill({ response: res, body })
  })
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.screenshot({ path: `audit/output/card-closed-${name}.png`, fullPage: true })
  await page.screenshot({ path: `audit/output/card-bets-${name}.png`, fullPage: true })
  const tab = page.getByRole('tab', { name: /^Datos/ })
  const n = await tab.count()
  if (n) await tab.first().click()
  const stayed = new URL(page.url()).pathname === '/'
  await page.screenshot({ path: `audit/output/card-data-${name}.png`, fullPage: true })
  const rows = page.locator('details > summary', { hasText: /Cara a cara|Primer game|Cómo vienen|Noticias/ })
  for (let i = 0; i < await rows.count(); i++) await rows.nth(i).click()
  await page.screenshot({ path: `audit/output/card-open-${name}.png`, fullPage: true })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, '| pestaña Datos:', n, '| sigue en el Dashboard:', stayed, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
