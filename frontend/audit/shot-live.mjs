// The En vivo page (every ATP match of ours in play, no follow button) and the card link.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  const links = await page.getByText('🔴 Ver en vivo').count()
  const follow = await page.getByRole('button', { name: /Seguir en vivo/ }).count()
  await page.goto(base + '/en-vivo', { waitUntil: 'networkidle' })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `audit/output/live-page-${name}.png` })
  console.log(name, '| enlaces ver en vivo:', links, '| botones seguir (deben ser 0):', follow, '| desborde:', overflow, '| errores:', errors.join(' / ') || 0)
  await page.close()
}
await browser.close()
