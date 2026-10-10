// Smoke check: the Fiabilidad search shows the career-by-surface card.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const out = process.argv[2] || 'audit/output'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
await page.goto(base, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: /Fiabilidad/ }).click()
await page.locator('input[list="reliability-players"]').fill('alcaraz')
await page.waitForTimeout(2500)
const card = page.locator('div', { hasText: 'Rendimiento por superficie (histórico)' }).last()
console.log('card visible:', await card.isVisible())
console.log('card text:', (await card.innerText()).replace(/\s+/g, ' ').slice(0, 400))
console.log('page errors:', errors)
await card.screenshot({ path: `${out}/career-card.png` })
await browser.close()
