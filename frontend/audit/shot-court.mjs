// The point-by-point court: mocks the tennis-simulation response (no scheduled match may exist) and plays a few points.
import { chromium } from 'playwright'
const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const id = process.env.MATCH_ID || 'TENNIS-12182773'
const fake = { available: true, bestOf: 3, player1: 'Musetti L.', player2: 'Hong S.', trust: 0.8, servePointsWon: { p1: 0.68, p2: 0.62 },
  matchWin: { p1: 0.7, p2: 0.3 }, setScores: [{ score: '2-0', p: 0.4 }], expectedGames: 20, tiebreak: 0.3, decider: 0.4,
  sets: [], serve: { p1: { hold: 0.85, breaksExpected: 1 }, p2: { hold: 0.78, breaksExpected: 2 } }, aces: { p1: null, p2: null }, h2h: null, note: 'prueba' }
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1100], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('**/tennis-simulation', (r) => r.fulfill({ json: fake }))
  await page.goto(`${base}/predictions/${process.env.PRED_ID}`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Justificación estadística' }).click()
  const sum = page.locator('summary', { hasText: 'Simulación del partido' })
  console.log(name, 'summary:', await sum.count())
  if (!(await sum.count())) { await page.screenshot({ path: `audit/output/court-${name}-none.png`, fullPage: true }); continue }
  await sum.first().click()
  await page.getByRole('button', { name: 'Auto' }).click()
  await page.waitForTimeout(2600)
  await page.screenshot({ path: `audit/output/court-${name}-a.png` })
  await page.waitForTimeout(900)
  await page.locator('section', { hasText: 'Jugar el partido' }).first().screenshot({ path: `audit/output/court-${name}-b.png` })
  console.log(name, 'errores:', errors.join(' / ') || 0, 'desborde:', await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
  await page.close()
}
await browser.close()
