// One-off full-page screenshots of /caja (desktop + mobile) for design review.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const out = process.argv[2] || 'audit/output'
const browser = await chromium.launch()
for (const [name, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
  const page = await browser.newPage({ viewport: { width, height } })
  await page.goto(`${base}/caja`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${out}/caja-${name}.png`, fullPage: true })
  const h = await page.evaluate(() => document.documentElement.scrollHeight)
  console.log(name, 'page height', h, 'px =', (h / height).toFixed(1), 'screens')
  await page.close()
}
await browser.close()
