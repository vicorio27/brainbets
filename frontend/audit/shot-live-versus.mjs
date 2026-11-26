// "Lo que pasa contra lo que simulamos" (En vivo): mocks /live/matches with a match in progress built from the real
// point-by-point of Fils-Jodar (backend/tests/application/fils_jodar_pbp.json), then serves a second reading ~30 s later
// so the court draws the new real point. No ATP match may be in play when this runs, hence the mock.
import { chromium } from 'playwright'
import fs from 'node:fs'

const base = process.env.AUDIT_BASE_URL || 'http://localhost:80'
const pbpAll = JSON.parse(fs.readFileSync('../backend/tests/application/fils_jodar_pbp.json', 'utf8'))

function reading(nGames, game, extra = {}) {
  const pbp = pbpAll.slice(0, nGames)
  const last = {}
  for (const g of pbp) last[g.set_number] = g.score
  const sets = Object.values(last).map((s) => s.split('-').map((x) => +x.trim()))
  const lg = pbp[pbp.length - 1]
  const st = (o) => ({ aces: 3, df: 1, winners: 14, ue: 12, last10: 5, first: [22, 32], second: [8, 18], points: [52, 99], ...o })
  return {
    status: 'Set 2', finished: false, winner: null, sets, setsWon: ['0', '1'], game, server: 'p1',
    stats: { p1: st(extra.p1 || {}), p2: st({ aces: 5, df: 2, winners: 11, ue: 15, last10: 5, first: [20, 29], second: [9, 21], points: [47, 99], ...(extra.p2 || {}) }) },
    pointsPlayed: 99 + (extra.add || 0), pointsWon: { p1: 52 + (extra.addP1 || 0), p2: 47 }, games: nGames, pbp,
    lastGame: { set: lg.set_number, game: lg.number_game, server: lg.player_served.startsWith('First') ? 'p1' : 'p2', lostServe: lg.serve_lost ? 'p1' : null },
  }
}
const payload = (rd) => ({
  matches: [{
    matchId: 'TENNIS-DEMO', player1: 'Fils A.', player2: 'Jodar R.', tournament: 'Demo', date: '2026-11-26', time: '11:00', state: 'en vivo',
    model: { pa: 0.66, pb: 0.64, bestOf: 3, trust: 0.8 }, reading: rd,
    events: [{ at: new Date().toISOString(), text: 'Winner de Fils A.: punto agresivo.' }],
    general: { points: rd.pointsPlayed, items: ['Fils A. juega con más ritmo.'] },
  }],
  upcoming: [], reading: true, calls: { today: 12, cap: 1500, pollSeconds: 30 }, feedError: null, note: 'prueba',
})

let current = payload(reading(14, '30 - 15'))
const browser = await chromium.launch()
for (const [name, width] of [['desktop', 1100], ['mobile', 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.route('**/live/matches*', (r) => r.fulfill({ json: current }))
  current = payload(reading(14, '30 - 15'))
  await page.goto(`${base}/en-vivo`, { waitUntil: 'networkidle' })
  const sec = page.locator('section', { hasText: 'Lo que pasa contra lo que simulamos' })
  console.log(name, 'sección:', await sec.count())
  await page.waitForTimeout(800)
  await sec.first().screenshot({ path: `audit/output/live-${name}-a.png` })
  // second reading: one more real point (a winner for player 1) -> the court draws it
  current = payload(reading(14, '40 - 15', { add: 1, addP1: 1, p1: { winners: 15, points: [53, 100] } }))
  if (name === 'desktop') {
    await page.waitForTimeout(31000)
    await page.waitForTimeout(1200)
    await sec.first().screenshot({ path: `audit/output/live-${name}-b.png` })
  }
  await page.getByText('Jugar el resto del partido desde este marcador').click()
  await page.getByRole('button', { name: 'Punto', exact: true }).first().click()
  await page.waitForTimeout(2500)
  await sec.first().screenshot({ path: `audit/output/live-${name}-c.png` })
  console.log(name, 'errores:', errors.join(' / ') || 0, 'desborde:', await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth))
  await page.close()
}
await browser.close()
