// Live mode of the tennis simulator: the real scoreboard (api-tennis get_livescore) read against the point model.
// pa = P(player 1 wins a point on his serve), pb = same for player 2 (from the point model, frozen before the match).
// Everything is the same model as the pre-match player: independent points, a 7-point tiebreak at 6-6 in every set.
// Exact probabilities (no sampling): points -> game -> tiebreak -> set -> match, from ANY state of the match.
import { cloneMatch, finishGame, newMatch } from './tennisSim.js'

// ---- exact win probability from a state -------------------------------------------------------------------------
function gameWinServer(ps, x, y) {
  if (x >= 4 && x - y >= 2) return 1
  if (y >= 4 && y - x >= 2) return 0
  if (x >= 3 && y >= 3) {
    const D = (ps * ps) / (ps * ps + (1 - ps) * (1 - ps))
    const d = x - y
    return d === 0 ? D : d === 1 ? ps + (1 - ps) * D : ps * D
  }
  return ps * gameWinServer(ps, x + 1, y) + (1 - ps) * gameWinServer(ps, x, y + 1)
}

// P(player 0 wins the game) when `s` serves and the points are (x0, x1) for players 0 and 1.
const p0WinsGame = (pa, pb, s, x0, x1) => (s === 0 ? gameWinServer(pa, x0, x1) : 1 - gameWinServer(pb, x1, x0))

function tbWin(pa, pb, t0, t1, first, memo) {
  if (t0 >= 7 && t0 - t1 >= 2) return 1
  if (t1 >= 7 && t1 - t0 >= 2) return 0
  if (t0 + t1 > 80) return 0.5
  const key = t0 * 100 + t1
  if (memo.has(key)) return memo.get(key)
  const s = Math.floor((t0 + t1 + 1) / 2) % 2 === 0 ? first : 1 - first
  const p0 = s === 0 ? pa : 1 - pb
  const v = p0 * tbWin(pa, pb, t0 + 1, t1, first, memo) + (1 - p0) * tbWin(pa, pb, t0, t1 + 1, first, memo)
  memo.set(key, v)
  return v
}

// Vector [w0&next0, w0&next1, w1&next0, w1&next1]: who wins the set and who serves the first game of the next one.
function makeEngine(pa, pb, bestOf) {
  const hold0 = gameWinServer(pa, 0, 0)
  const hold1 = gameWinServer(pb, 0, 0)
  const setMemo = new Map()
  const matchMemo = new Map()
  const tbVec = (first, t0 = 0, t1 = 0) => {
    const p = tbWin(pa, pb, t0, t1, first, new Map())
    const ns = 1 - first
    const v = [0, 0, 0, 0]
    v[ns] = p // player 0 wins
    v[2 + ns] = 1 - p
    return v
  }
  const add = (acc, v, k) => { for (let i = 0; i < 4; i++) acc[i] += k * v[i] }
  const afterGame = (g0, g1, s, w) => {
    const n0 = w === 0 ? g0 + 1 : g0
    const n1 = w === 1 ? g1 + 1 : g1
    const hi = Math.max(n0, n1)
    if (hi >= 6 && Math.abs(n0 - n1) >= 2) {
      const v = [0, 0, 0, 0]
      v[(n0 > n1 ? 0 : 2) + (1 - s)] = 1
      return v
    }
    if (n0 === 6 && n1 === 6) return tbVec(1 - s)
    return setOut(n0, n1, 1 - s)
  }
  const setOut = (g0, g1, s) => {
    if (g0 === 6 && g1 === 6) return tbVec(s)
    const key = g0 * 1000 + g1 * 10 + s
    if (setMemo.has(key)) return setMemo.get(key)
    const pg = s === 0 ? hold0 : 1 - hold1
    const acc = [0, 0, 0, 0]
    add(acc, afterGame(g0, g1, s, 0), pg)
    add(acc, afterGame(g0, g1, s, 1), 1 - pg)
    setMemo.set(key, acc)
    return acc
  }
  const need = Math.ceil(bestOf / 2)
  const matchFrom = (s0, s1, first) => {
    if (s0 >= need) return 1
    if (s1 >= need) return 0
    const key = s0 * 100 + s1 * 10 + first
    if (matchMemo.has(key)) return matchMemo.get(key)
    const o = setOut(0, 0, first)
    const v = o[0] * matchFrom(s0 + 1, s1, 0) + o[1] * matchFrom(s0 + 1, s1, 1) +
      o[2] * matchFrom(s0, s1 + 1, 0) + o[3] * matchFrom(s0, s1 + 1, 1)
    matchMemo.set(key, v)
    return v
  }
  const fromVec = (m, v) => v[0] * matchFrom(m.setsWon[0] + 1, m.setsWon[1], 0) + v[1] * matchFrom(m.setsWon[0] + 1, m.setsWon[1], 1) +
    v[2] * matchFrom(m.setsWon[0], m.setsWon[1] + 1, 0) + v[3] * matchFrom(m.setsWon[0], m.setsWon[1] + 1, 1)
  return { tbVec, afterGame, setOut, matchFrom, fromVec }
}

// P(player 1 wins the match) from the state `m` (same shape as tennisSim.newMatch).
export function winProb(m, pa, pb) {
  if (m.over) return m.winner === 0 ? 1 : 0
  const E = makeEngine(pa, pb, m.bestOf)
  const [g0, g1] = m.cur
  let v
  if (m.tb || (g0 === 6 && g1 === 6)) {
    v = E.tbVec(m.tbFirst ?? m.server, m.tb ? m.pts[0] : 0, m.tb ? m.pts[1] : 0)
  } else {
    const s = m.server
    const pg = p0WinsGame(pa, pb, s, m.pts[0], m.pts[1])
    v = [0, 0, 0, 0]
    const a = E.afterGame(g0, g1, s, 0)
    const b = E.afterGame(g0, g1, s, 1)
    for (let i = 0; i < 4; i++) v[i] = pg * a[i] + (1 - pg) * b[i]
  }
  return E.fromVec(m, v)
}

// Before the first point: the first server is a coin toss, so average the two.
export function preMatchProb(bestOf, pa, pb) {
  const E = makeEngine(pa, pb, bestOf)
  return 0.5 * E.matchFrom(0, 0, 0) + 0.5 * E.matchFrom(0, 0, 1)
}

// ---- real scoreboard -> simulator state -------------------------------------------------------------------------
const PT = { 0: 0, 15: 1, 30: 2, 40: 3, A: 4, AD: 4 }
const sideIdx = (t) => (t === 'p1' ? 0 : t === 'p2' ? 1 : null)
const pbpSide = (t) => {
  const x = String(t || '').toLowerCase()
  return x.startsWith('first') ? 0 : x.startsWith('second') ? 1 : null
}
const setDone = (a, b) => {
  const hi = Math.max(a, b)
  const lo = Math.min(a, b)
  return (hi >= 6 && hi - lo >= 2) || (hi === 7 && lo >= 5)
}

function parseGame(text, tb) {
  if (!text) return [0, 0]
  const parts = String(text).split('-').map((x) => x.trim().toUpperCase())
  if (parts.length !== 2) return [0, 0]
  const f = (x) => (tb ? parseInt(x, 10) || 0 : PT[x] ?? 0)
  return [f(parts[0]), f(parts[1])]
}

// Reading of /live/matches (`reading`) -> {m, serverGuessed}. `m` is a tennisSim state continuing the REAL score.
export function stateFromReading(reading, bestOf) {
  if (!reading) return null
  const m = newMatch(bestOf, () => 0)
  const need = Math.ceil(bestOf / 2)
  m.sets = []
  m.cur = [0, 0]
  const sets = reading.sets || []
  for (let i = 0; i < sets.length; i++) {
    const [a, b] = sets[i]
    const last = i === sets.length - 1
    if (setDone(a, b) || (reading.finished && last)) {
      m.sets.push([a, b])
      m.setsWon[a > b ? 0 : 1] += 1
    } else {
      m.cur = [a, b]
    }
  }
  if (reading.finished || m.setsWon[0] >= need || m.setsWon[1] >= need) {
    m.over = true
    m.winner = m.setsWon[0] > m.setsWon[1] ? 0 : 1
    return { m, serverGuessed: false }
  }
  const inTb = m.cur[0] === 6 && m.cur[1] === 6
  m.tb = inTb
  m.pts = parseGame(reading.game, inTb)
  let server = sideIdx(reading.server)
  let guessed = false
  if (server == null) {
    const lg = reading.lastGame
    const prev = lg && sideIdx(lg.server)
    server = prev == null ? 0 : 1 - prev
    guessed = true
  }
  m.server = server
  if (inTb) {
    const t = m.pts[0] + m.pts[1]
    m.tbFirst = Math.floor((t + 1) / 2) % 2 === 0 ? server : 1 - server
  }
  return { m, serverGuessed: guessed }
}

// P(player 1 wins) from the real score; if the feed does not say who serves, average the two options.
export function liveWinProb(state, pa, pb) {
  if (!state) return null
  const { m, serverGuessed } = state
  if (!serverGuessed || m.over || m.tb) return winProb(m, pa, pb)
  const other = cloneMatch(m)
  other.server = 1 - m.server
  return 0.5 * winProb(m, pa, pb) + 0.5 * winProb(other, pa, pb)
}

// Win probability of player 1 at the end of every real game, rebuilt from the point-by-point.
// Returns [{p, event, set, game}] (first item = before the match) or null if the replay does not match the scoreboard.
export function winPath(pbp, bestOf, pa, pb, state) {
  if (!Array.isArray(pbp) || !pbp.length) return null
  const first = pbpSide(pbp[0].player_served)
  if (first == null) return null
  const m = newMatch(bestOf, () => 0)
  m.server = first
  const out = [{ p: winProb(m, pa, pb), event: 'start', set: 1, game: 0 }]
  for (const g of pbp) {
    const w = pbpSide(g.serve_winner)
    const s = pbpSide(g.player_served)
    if (w == null || s == null || m.over) continue
    if (!m.tb) m.server = s
    const setNo = m.sets.length + 1
    const ev = finishGame(m, w, s)
    out.push({ p: winProb(m, pa, pb), event: ev, set: setNo, game: out.length, w })
  }
  if (state) {
    const t = state.m
    const same = JSON.stringify([m.sets, m.cur, m.setsWon]) === JSON.stringify([t.sets, t.cur, t.setsWon])
    if (!same) return null
  }
  return out
}

// ---- real against what the model expected ---------------------------------------------------------------------
const servePts = (st) => {
  if (!st) return null
  if (st.servePts && st.servePts[1]) return st.servePts
  if (st.first && st.second) return [st.first[0] + st.second[0], st.first[1] + st.second[1]]
  return null
}

// Per player: serve points won (real) against the model's serve-point probability, plus the points each should have won.
export function realVsExpected(reading, pa, pb) {
  if (!reading) return null
  const s1 = servePts(reading.stats?.p1)
  const s2 = servePts(reading.stats?.p2)
  if (!s1 || !s2) return null
  const row = (s, p) => {
    const n = s[1]
    const rate = n ? s[0] / n : 0
    const z = n ? (rate - p) / Math.sqrt((p * (1 - p)) / n) : 0
    const level = n < 20 ? 'pronto' : Math.abs(z) < 1 ? 'normal' : z > 0 ? (z >= 2 ? 'muy_alto' : 'alto') : z <= -2 ? 'muy_bajo' : 'bajo'
    return { won: s[0], n, rate, expected: p, z, level }
  }
  const total = [s1[1] + s2[1], s1[0] + s2[0]]
  const real = [reading.pointsWon?.p1 ?? null, reading.pointsWon?.p2 ?? null]
  return {
    p1: row(s1, pa),
    p2: row(s2, pb),
    points: {
      real,
      expected: [pa * s1[1] + (1 - pb) * s2[1], pb * s2[1] + (1 - pa) * s1[1]],
      played: total[0],
    },
  }
}

// What a new real reading says about the points since the previous one (for the animated court).
export function newPoints(prev, cur) {
  if (!prev || !cur) return null
  const n = (cur.pointsPlayed || 0) - (prev.pointsPlayed || 0)
  if (n <= 0) return { n: 0 }
  const won = [(cur.pointsWon?.p1 || 0) - (prev.pointsWon?.p1 || 0), (cur.pointsWon?.p2 || 0) - (prev.pointsWon?.p2 || 0)]
  const d = (side, key) => Math.max(0, (cur.stats?.[side]?.[key] || 0) - (prev.stats?.[side]?.[key] || 0))
  const delta = { p1: { aces: d('p1', 'aces'), df: d('p1', 'df'), winners: d('p1', 'winners'), ue: d('p1', 'ue') },
    p2: { aces: d('p2', 'aces'), df: d('p2', 'df'), winners: d('p2', 'winners'), ue: d('p2', 'ue') } }
  if (n !== 1) return { n, won, delta }
  const w = won[0] > 0 ? 0 : 1
  const ws = w === 0 ? 'p1' : 'p2'
  const ls = w === 0 ? 'p2' : 'p1'
  const kind = delta[ws].aces ? 'ace' : delta[ls].df ? 'doublefault' : delta[ws].winners ? 'winner' : delta[ls].ue ? 'error' : 'rally'
  return { n, won, delta, winner: w, kind }
}
