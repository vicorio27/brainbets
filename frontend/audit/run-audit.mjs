/**
 * BrainBets UI audit.
 *
 * Navigates every dashboard tab / route at three viewports and records:
 *  - a full-page screenshot            -> audit/output/<view>__<viewport>.png
 *  - axe-core accessibility violations (wcag2a + wcag2aa)
 *  - horizontal overflow (page wider than the viewport) + offending elements
 *  - navigation timing (DCL / load) and resource weight
 *
 * A machine-readable summary is written to audit/output/report.json and a
 * human summary is printed at the end.
 *
 * Usage:
 *   AUDIT_BASE_URL=http://localhost:80 node audit/run-audit.mjs
 *   (default base URL is http://localhost:80)
 */
import { chromium } from 'playwright'
import { AxeBuilder } from '@axe-core/playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const BASE_URL = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), 'output')

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'desktop', width: 1440, height: 900 },
]

// Each view = a route plus an optional in-page action (dashboard tabs are
// client state, not routes, so we click the tab button by its label).
const VIEWS = [
  { slug: 'dashboard-hoy', path: '/', tab: 'Hoy' },
  { slug: 'dashboard-torneos', path: '/', tab: 'Torneos' },
  { slug: 'dashboard-apuestas', path: '/', tab: 'Apuestas' },
  { slug: 'dashboard-fiabilidad', path: '/', tab: 'Fiabilidad' },
  {
    slug: 'dashboard-fiabilidad-busqueda',
    path: '/',
    tab: 'Fiabilidad',
    action: async (page) => {
      const input = page.getByPlaceholder(/Buscar jugador/i)
      await input.fill('a')
      await page.waitForTimeout(400)
    },
  },
  { slug: 'dashboard-historico', path: '/', tab: 'Histórico' },
  { slug: 'predicciones', path: '/predictions' },
  { slug: 'analytics', path: '/analytics' },
]

async function measureOverflow(page) {
  return page.evaluate(() => {
    const docWidth = document.documentElement.scrollWidth
    const winWidth = window.innerWidth
    const overflowPx = docWidth - winWidth
    const offenders = []
    if (overflowPx > 1) {
      for (const el of document.querySelectorAll('*')) {
        const r = el.getBoundingClientRect()
        if (r.right > winWidth + 1 && r.width > 0 && r.height > 0) {
          offenders.push({
            tag: el.tagName.toLowerCase(),
            cls: (el.className && el.className.toString().slice(0, 80)) || '',
            right: Math.round(r.right),
            width: Math.round(r.width),
          })
        }
      }
    }
    return { docWidth, winWidth, overflowPx, offenders: offenders.slice(0, 8) }
  })
}

async function measureTiming(page) {
  return page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {}
    const res = performance.getEntriesByType('resource')
    const bytes = res.reduce((n, r) => n + (r.transferSize || 0), 0)
    return {
      domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd || 0),
      loadMs: Math.round(nav.loadEventEnd || 0),
      resources: res.length,
      transferKB: Math.round(bytes / 1024),
    }
  })
}

async function run() {
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  const report = { baseUrl: BASE_URL, generatedAt: new Date().toISOString(), results: [] }

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    })
    for (const view of VIEWS) {
      const page = await context.newPage()
      const consoleErrors = []
      page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text().slice(0, 200)))
      page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 200)))

      const settle = async () => {
        await page.waitForLoadState('networkidle').catch(() => {})
        // The dashboard gates all content behind a "Cargando datos..." spinner
        // that re-appears on every tab switch.
        await page
          .locator('text=Cargando datos')
          .waitFor({ state: 'hidden', timeout: 15000 })
          .catch(() => {})
        await page.waitForTimeout(500)
      }

      const entry = { view: view.slug, viewport: vp.name, url: BASE_URL + view.path }
      try {
        await page.goto(BASE_URL + view.path, { waitUntil: 'networkidle', timeout: 30000 })
        await settle()
        if (view.tab) {
          await page.getByRole('button', { name: view.tab, exact: true }).click()
          await settle()
        }
        if (view.action) await view.action(page)
        await page.waitForTimeout(400)

        const shot = `${view.slug}__${vp.name}.png`
        await page.screenshot({ path: join(OUT_DIR, shot), fullPage: true })
        entry.screenshot = `output/${shot}`

        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
        const byImpact = {}
        for (const v of axe.violations) byImpact[v.impact] = (byImpact[v.impact] || 0) + 1
        entry.a11y = {
          violations: axe.violations.length,
          byImpact,
          rules: axe.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
        }

        entry.overflow = await measureOverflow(page)
        entry.timing = await measureTiming(page)
        entry.consoleErrors = consoleErrors
      } catch (err) {
        entry.error = String(err).slice(0, 300)
      }
      report.results.push(entry)
      await page.close()
      const flag = entry.error
        ? 'ERR'
        : `${entry.a11y?.violations ?? '?'} a11y, ${entry.overflow?.overflowPx > 1 ? entry.overflow.overflowPx + 'px overflow' : 'no overflow'}`
      console.log(`  [${vp.name}] ${view.slug.padEnd(30)} ${flag}`)
    }
    await context.close()
  }
  await browser.close()

  await writeFile(join(OUT_DIR, 'report.json'), JSON.stringify(report, null, 2))

  // ---- summary ----
  console.log('\n=== SUMMARY ===')
  const overflows = report.results.filter((r) => r.overflow?.overflowPx > 1)
  const a11y = report.results.filter((r) => r.a11y?.violations > 0)
  const errs = report.results.filter((r) => r.error || (r.consoleErrors || []).length)

  console.log(`\nHorizontal overflow: ${overflows.length} view/viewport combos`)
  for (const r of overflows) {
    console.log(`  ${r.view} @ ${r.viewport}: +${r.overflow.overflowPx}px`)
    for (const o of r.overflow.offenders) console.log(`      <${o.tag} class="${o.cls}"> right=${o.right}`)
  }

  const ruleAgg = {}
  for (const r of a11y) for (const rule of r.a11y.rules) {
    ruleAgg[rule.id] = ruleAgg[rule.id] || { impact: rule.impact, count: 0, views: new Set() }
    ruleAgg[rule.id].count += 1
    ruleAgg[rule.id].views.add(`${r.view}@${r.viewport}`)
  }
  console.log(`\nAccessibility (axe wcag2a/aa): ${Object.keys(ruleAgg).length} distinct rules`)
  for (const [id, v] of Object.entries(ruleAgg).sort((a, b) => b[1].count - a[1].count)) {
    console.log(`  [${v.impact}] ${id} — ${v.count} occurrence(s) across ${v.views.size} view(s)`)
  }

  console.log(`\nConsole errors / page errors: ${errs.length} view/viewport combos`)
  for (const r of errs) console.log(`  ${r.view}@${r.viewport}: ${r.error || r.consoleErrors.join(' | ')}`)

  const slowest = [...report.results].filter((r) => r.timing).sort((a, b) => b.timing.loadMs - a.timing.loadMs)[0]
  if (slowest) console.log(`\nSlowest load: ${slowest.view}@${slowest.viewport} ${slowest.timing.loadMs}ms, ${slowest.timing.transferKB}KB over ${slowest.timing.resources} requests`)

  console.log(`\nScreenshots + report.json in ${OUT_DIR}`)
}

run().catch((e) => {
  console.error(e)
  process.exit(1)
})
