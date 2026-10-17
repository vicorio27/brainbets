// Screenshot of one match's predictions with the point-model box and "Puntos" column, plus console errors.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const matchId = process.env.MATCH_ID || 'TENNIS-12171477'
const date = process.env.MATCH_DATE || '2026-10-17'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(`${base}/predictions?matchId=${matchId}&date=${date}`, { waitUntil: 'networkidle' })
  const box = await page.getByText('Modelo de puntos', { exact: false }).count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'recuadro de puntos:', box, '| desborde:', overflow, '| errores:', errors.length, errors.join(' | '))
  await page.screenshot({ path: `audit/output/points-${name}.png`, fullPage: true })
  await page.close()
}
await browser.close()
