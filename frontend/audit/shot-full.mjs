// Full-page Dashboard capture + checks that the folded sections open without navigating away.
import { chromium } from 'playwright'
const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.screenshot({ path: `audit/output/full-${name}.png`, fullPage: true })
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  // a folded section must open in place, not navigate to /predictions
  const first = page.locator('details > summary', { hasText: 'Games y puntos por set' })
  if (await first.count()) { await first.click(); }
  const more = page.locator('details > summary', { hasText: 'Más datos' })
  const nMore = await more.count()
  if (nMore) { await more.first().click() }
  const stayed = new URL(page.url()).pathname === '/'
  console.log(name, '| alto:', height, 'px | desborde:', overflow, '| "Más datos":', nMore, '| sigue en el Dashboard:', stayed, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
