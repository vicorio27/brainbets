// "How he is playing lately" lines on the match cards and in "Los dos lados".
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const lines = await page.getByText('📊').count()
  const first = page.getByText('📊').first()
  if (lines) await first.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `audit/output/level-dash-${name}.png` })
  await page.goto(base + '/predictions', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Los dos lados', exact: true }).click()
  const sum = page.locator('summary', { hasText: '📊' }).first()
  if (await sum.count()) await sum.click()
  await page.screenshot({ path: `audit/output/level-sides-${name}.png` })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, '| líneas de nivel en tarjetas:', lines, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
