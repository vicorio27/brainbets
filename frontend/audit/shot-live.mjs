// "Seguir en vivo" on a match card and the En vivo page.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const buttons = await page.getByRole('button', { name: /Seguir en vivo|Siguiendo en vivo/ }).count()
  const b = page.getByRole('button', { name: /Seguir en vivo|Siguiendo en vivo/ }).first()
  if (buttons) await b.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `audit/output/live-card-${name}.png` })
  await page.goto(base + '/en-vivo', { waitUntil: 'networkidle' })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `audit/output/live-page-${name}.png` })
  console.log(name, '| botones seguir:', buttons, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
