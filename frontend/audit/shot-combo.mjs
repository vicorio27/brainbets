// Builds a combo from the "Lo más probable" picks and screenshots the bar and the panel.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.evaluate(() => localStorage.removeItem('brainbets.combo.v1'))
  await page.reload({ waitUntil: 'networkidle' })
  const adds = page.getByRole('button', { name: /Agregar a mi combinada/ })
  const labels = await adds.evaluateAll((els) => els.map((e) => e.closest('.rounded.border')?.innerText.length + '|' + e.getAttribute('aria-label')))
  console.log(name, 'botones +:', labels.length)
  // first pick of the first card, then a pick of another card, then a second pick of that same card
  const cards = page.locator('div.rounded.border:has(button[aria-label^="Agregar a mi combinada"])')
  await cards.nth(0).locator('button[aria-label^="Agregar"]').first().click()
  await cards.nth(1).locator('button[aria-label^="Agregar"]').nth(1).click()
  await cards.nth(1).locator('button[aria-label^="Agregar"]').first().click()
  const clash = await page.getByText('cambiarla por esta').count()
  await page.screenshot({ path: `audit/output/combo-clash-${name}.png` })
  await page.getByRole('button', { name: /Mi combinada \(2\)/ }).click()
  await page.screenshot({ path: `audit/output/combo-${name}.png` })
  await page.reload({ waitUntil: 'networkidle' })
  const kept = await page.getByRole('button', { name: /Mi combinada \(2\)/ }).count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, '| aviso mismo partido:', clash, '| sigue tras recargar:', kept, '| desborde:', overflow, '| errores:', errors.length, errors.slice(0, 2))
  await page.close()
}
await browser.close()
