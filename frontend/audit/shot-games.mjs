// Screenshot of a tennis match card with the games-model box, plus console errors.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const box = page.getByText('Modelo de games:').first()
  const n = await page.getByText('Modelo de games:').count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'tarjetas con modelo de games:', n, '| desborde:', overflow, '| errores:', errors.length)
  if (n) await box.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `audit/output/games-${name}.png` })
  await page.close()
}
await browser.close()
