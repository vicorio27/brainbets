// Lists the elements failing WCAG AA colour contrast on each route (the main audit only counts them).
import { chromium } from 'playwright'
import AxeBuilder from '@axe-core/playwright'

const BASE = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const routes = ['/', '/matches', '/predictions', '/analytics', '/caja']
const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const page = await context.newPage()

for (const route of routes) {
  await page.goto(BASE + route, { waitUntil: 'networkidle' })
  const { violations } = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze()
  const seen = new Set()
  for (const v of violations) {
    for (const n of v.nodes) {
      const cls = (n.html.match(/class="([^"]*)"/) || [])[1] || n.html.slice(0, 80)
      const data = n.any[0]?.data || {}
      const key = `${cls} | ${data.fgColor} on ${data.bgColor} = ${data.contrastRatio}`
      if (!seen.has(key)) seen.add(key)
    }
  }
  console.log(route, seen.size ? '' : 'sin fallos')
  for (const k of seen) console.log('   ', k)
}
await browser.close()
