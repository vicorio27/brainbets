// Screenshots of the "Apuesta del día" card in its three colours. The real data gives one of
// them; the other two are forced by shifting every anchored edge in the API response.
import { chromium } from 'playwright'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const out = process.argv[2] || 'audit/output'
const browser = await chromium.launch()
for (const [name, shift] of [['real', 0], ['leve', 0.06], ['clara', 0.12]]) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 520 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  if (shift) {
    await page.route('**/api/v1/predictions/latest', async (route) => {
      const res = await route.fetch()
      const body = await res.json()
      for (const p of body.predictions || []) {
        if (p.betEdge == null) continue
        const odds = (1 + p.betEdge) / p.betProbability
        p.betEdge += shift
        p.betProbability = (1 + p.betEdge) / odds
        p.modelWeight = 0.2
      }
      await route.fulfill({ response: res, json: body })
    })
  }
  await page.goto(base + '/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)
  const card = page.locator('.rounded-2xl').first()
  console.log(name, '→', (await card.innerText()).replace(/\s+/g, ' ').slice(0, 330), '| errores:', errors.length)
  await card.screenshot({ path: `${out}/pod-${name}.png` })
  await page.close()
}
await browser.close()
