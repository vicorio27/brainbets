// Smoke check: the Caja "Laboratorio" tab renders the shadow-model report.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const out = process.argv[2] || 'audit/output'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))
await page.goto(`${base}/caja`, { waitUntil: 'networkidle' })
await page.waitForTimeout(4000)
await page.getByRole('tab', { name: /Laboratorio/ }).click()
await page.waitForTimeout(300)
await page.screenshot({ path: `${out}/caja-tab-laboratorio.png`, fullPage: true })
console.log('status badge:', await page.getByText('Juntando muestra').count(), '| rows:', await page.locator('tbody tr:visible').count())
console.log('page errors:', errors)
await browser.close()
