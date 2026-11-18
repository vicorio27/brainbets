// Conservative / risky selector (Predicciones) and the conservative bet of the day (Dashboard).
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const hero = await page.getByText(/Apuesta del día · conservadora|la más segura de/).count()
  await page.screenshot({ path: `audit/output/modes-dash-${name}.png` })
  await page.goto(base + '/predictions', { waitUntil: 'networkidle' })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `audit/output/modes-cons-${name}.png` })
  await page.getByRole('button', { name: 'Combinada', exact: true }).click()
  await page.screenshot({ path: `audit/output/modes-combo-${name}.png` })
  await page.getByRole('button', { name: 'Arriesgada', exact: true }).click()
  await page.getByText('📈 Movimiento de cuotas y gangas').click()
  await page.screenshot({ path: `audit/output/modes-risky-${name}.png`, fullPage: false })
  await page.getByRole('button', { name: 'Los dos lados', exact: true }).click()
  await page.screenshot({ path: `audit/output/modes-sides-${name}.png` })
  await page.goto(base + '/predictions?matchId=TENNIS-12179696&date=2026-11-18', { waitUntil: 'networkidle' })
  await page.screenshot({ path: `audit/output/modes-match-${name}.png` })
  console.log(name, '| tarjeta conservadora:', hero, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
