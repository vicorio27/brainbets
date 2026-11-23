// The Fútbol page (La Liga + Premier League) and a check that the tennis dashboard shows no football.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const footballOnDashboard = await page.locator('h2:has-text("Fútbol")').count()
  await page.goto(base + '/futbol', { waitUntil: 'networkidle' })
  const cards = await page.locator('h2').count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `audit/output/football-${name}.png`, fullPage: true })
  console.log(name, '| ⚽ en el dashboard de tenis (debe ser 0):', footballOnDashboard, '| secciones:', cards, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
