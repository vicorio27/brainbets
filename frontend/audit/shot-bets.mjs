// Screenshot of the Apuestas tab (best bets still to play) plus the page's console errors.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Apuestas', exact: true }).click()
  await page.waitForTimeout(600)
  const rows = await page.locator('[aria-label="Mejores apuestas por jugar"] tbody tr').count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'filas:', rows, '| desborde horizontal:', overflow, '| errores:', errors.length)
  await page.screenshot({ path: `audit/output/bets-${name}.png`, fullPage: false })
  await page.getByRole('button', { name: 'Más seguras', exact: true }).click()
  await page.locator('summary', { hasText: 'Cómo les fue' }).click()
  await page.waitForTimeout(300)
  const safeRows = await page.locator('[aria-label="Apuestas más seguras por jugar"] tbody tr').count()
  const safeOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'más seguras filas:', safeRows, '| desborde:', safeOverflow, '| errores:', errors.length)
  await page.locator('[aria-label="Apuestas más seguras por jugar"]').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `audit/output/bets-safe-${name}.png`, fullPage: false })
  await page.close()
}
await browser.close()
