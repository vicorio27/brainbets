// Point-by-point tennis simulator from the two serve-point probabilities of the point model.
// pa = P(player 1 wins a point on his serve), pb = same for player 2. Every point is an independent draw:
// no momentum, nerves or fatigue. A 7-point tiebreak is played at 6-6 in every set (also the last one).
export const POINT_LABELS = ['0', '15', '30', '40']

export function newMatch(bestOf = 3, rng = Math.random) {
  return {
    bestOf, server: rng() < 0.5 ? 0 : 1, sets: [], cur: [0, 0], pts: [0, 0], tb: false, tbFirst: 0,
    setsWon: [0, 0], over: false, winner: null,
  }
}

export const serverNow = (m) => {
  if (!m.tb) return m.server
  const total = m.pts[0] + m.pts[1]
  return Math.floor((total + 1) / 2) % 2 === 0 ? m.tbFirst : 1 - m.tbFirst
}

export function pointText(m) {
  if (m.tb) return `${m.pts[0]}-${m.pts[1]}`
  const [a, b] = m.pts
  if (a >= 3 && b >= 3) return a === b ? 'Iguales' : a > b ? 'Ventaja 1' : 'Ventaja 2'
  return `${POINT_LABELS[Math.min(a, 3)]}-${POINT_LABELS[Math.min(b, 3)]}`
}

// Plays one point. Returns {winner, server, event} where event is '' | 'game' | 'set' | 'match' | 'break'.
export function playPoint(m, pa, pb, rng = Math.random) {
  if (m.over) return null
  const s = serverNow(m)
  const pServer = s === 0 ? pa : pb
  const serverWins = rng() < pServer
  const w = serverWins ? s : 1 - s
  m.pts[w] += 1
  let event = ''
  const [a, b] = m.pts
  const need = m.tb ? 7 : 4
  const won = m.pts[w] >= need && m.pts[w] - m.pts[1 - w] >= 2
  if (won) {
    m.cur[w] += 1
    event = w !== s && !m.tb ? 'break' : 'game'
    const wasTb = m.tb
    m.pts = [0, 0]
    m.tb = false
    const [g, h] = m.cur
    const setDone = wasTb || (g >= 6 && g - h >= 2) || (h >= 6 && h - g >= 2)
    if (setDone) {
      m.sets.push([...m.cur])
      m.setsWon[w] += 1
      m.cur = [0, 0]
      event = 'set'
      if (m.setsWon[w] === Math.ceil(m.bestOf / 2)) { m.over = true; m.winner = w; event = 'match' }
    }
    if (!m.over) {
      // the game just finished: next game is served by the other player (after a tiebreak, the one who received first)
      m.server = wasTb ? 1 - m.tbFirst : 1 - s
      if (m.cur[0] === 6 && m.cur[1] === 6) { m.tb = true; m.tbFirst = m.server }
    }
  }
  return { winner: w, server: s, event, a, b }
}

export function playUntil(m, pa, pb, stop, rng = Math.random) {
  const log = []
  let guard = 0
  while (!m.over && guard++ < 5000) {
    const r = playPoint(m, pa, pb, rng)
    log.push(r)
    if (stop(r)) break
  }
  return log
}

export function monteCarlo(bestOf, pa, pb, n = 2000, rng = Math.random) {
  let p1 = 0, tb = 0, games = 0, decider = 0
  const scores = {}
  for (let i = 0; i < n; i++) {
    const m = newMatch(bestOf, rng)
    let hadTb = false
    while (!m.over) {
      if (m.tb) hadTb = true
      playPoint(m, pa, pb, rng)
    }
    if (m.winner === 0) p1 += 1
    if (hadTb) tb += 1
    games += m.sets.reduce((x, s) => x + s[0] + s[1], 0)
    if (m.setsWon[0] + m.setsWon[1] === bestOf) decider += 1
    const key = `${m.setsWon[0]}-${m.setsWon[1]}`
    scores[key] = (scores[key] || 0) + 1
  }
  return {
    n, p1: p1 / n, tiebreak: tb / n, games: games / n, decider: decider / n,
    scores: Object.entries(scores).map(([score, c]) => ({ score, p: c / n })).sort((x, y) => y.p - x.p),
  }
}
