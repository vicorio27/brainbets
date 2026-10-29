// Registers a combo from the Dashboard, checks it in Mis apuestas, then deletes it (a test bet).
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1280], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('dialog', (d) => d.accept())
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.evaluate(() => localStorage.removeItem('brainbets.combo.v1'))
  await page.reload({ waitUntil: 'networkidle' })
  const cards = page.locator('div.rounded.border:has(button[aria-label^="Agregar a mi combinada"])')
  const n = await cards.count()
  // the two last cards: the latest start times, the least likely to have begun
  await cards.nth(n - 1).locator('button[aria-label^="Agregar"]').first().click()
  await cards.nth(n - 2).locator('button[aria-label^="Agregar"]').first().click()
  await page.getByRole('button', { name: /Mi combinada \(2\)/ }).click()
  await page.getByRole('button', { name: /Registrar combinada/ }).click()
  await page.waitForTimeout(1500)
  const ok = await page.getByText('Registrada. Se liquida sola').count()
  const err = await page.locator('p.text-red-700').allInnerTexts()
  await page.screenshot({ path: `audit/output/mybets-registered-${name}.png` })
  await page.getByRole('link', { name: 'ver Mis apuestas' }).first().click()
  await page.getByText('Combinada de 2').first().waitFor()
  const pending = await page.getByText('Pendiente', { exact: true }).count()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  await page.screenshot({ path: `audit/output/mybets-${name}.png`, fullPage: true })
  await page.getByRole('button', { name: /borrar \(registrada por error\)/ }).first().click()
  await page.waitForTimeout(1500)
  const left = await page.getByRole('button', { name: /borrar \(registrada por error\)/ }).count()
  console.log(name, '| registrada:', ok, err, '| pendientes en la lista:', pending, '| quedan tras borrar:', left, '| desborde:', overflow, '| errores:', errors.length, errors.slice(0, 2))
  await page.close()
}
await browser.close()
