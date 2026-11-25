// "Lo más probable" of a football match. Pure functions, football only.
// The probability of each pick is the bookmaker's own (margin removed) when it prices it, and the
// Poisson model's otherwise (source "modelo"). Neither has been shown to beat the price: it is
// "what usually happens", not a value signal.

const fact = (n) => (n <= 1 ? 1 : n * fact(n - 1))
const pois = (l, k) => Math.exp(-l) * Math.pow(l, k) / fact(k)

export function modelProbs(h, a) {
  if (!(h > 0) || !(a > 0)) return null
  let home = 0, draw = 0, away = 0
  for (let i = 0; i <= 10; i++) for (let j = 0; j <= 10; j++) {
    const p = pois(h, i) * pois(a, j)
    if (i > j) home += p; else if (i === j) draw += p; else away += p
  }
  const t = home + draw + away
  home /= t; draw /= t; away /= t
  const total = h + a
  const over = (k) => 1 - Array.from({ length: Math.floor(k) + 1 }, (_, i) => pois(total, i)).reduce((x, y) => x + y, 0)
  return {
    home, draw, away, over05: over(0.5), over15: over(1.5), over25: over(2.5), over35: over(3.5), over45: over(4.5),
    btts: (1 - Math.exp(-h)) * (1 - Math.exp(-a)), homeScores: 1 - Math.exp(-h), awayScores: 1 - Math.exp(-a)
  }
}

const fair2 = (x, y) => (x > 1 && y > 1 ? (1 / x) / (1 / x + 1 / y) : null)

export function likelyPicks(match) {
  const m = modelProbs(match.expectedHomeGoals, match.expectedAwayGoals)
  const om = match.oddsMarkets || {}
  const ou = om.overUnder || {}
  const out = []
  // kind + selector say how the bet settles (user_bets_service): the picks can be registered in "Mis apuestas".
  const add = (key, text, house, model, odds, kind, selector) => {
    const p = house ?? model
    if (p == null) return
    out.push({ key, text, prob: p, source: house != null ? 'casa' : 'modelo', odds: odds || null, kind, selector })
  }
  for (const line of ['1.5', '2.5', '3.5']) {
    const l = ou[line]
    if (!l) continue
    const o = fair2(l.over, l.under)
    const mk = m ? m['over' + line.replace('.', '')] : null
    add('o' + line, `Más de ${line} goles`, o, mk, l.over, 'fGoals', { line: +line, pick: 'mas' })
    add('u' + line, `Menos de ${line} goles`, o == null ? null : 1 - o, mk == null ? null : 1 - mk, l.under, 'fGoals', { line: +line, pick: 'menos' })
  }
  if (m) {
    add('o0.5', 'Más de 0.5 goles', null, m.over05, null, 'fGoals', { line: 0.5, pick: 'mas' })
    add('u4.5', 'Menos de 4.5 goles', null, 1 - m.over45, null, 'fGoals', { line: 4.5, pick: 'menos' })
    add('homeScores', `${match.homeTeam} marca`, null, m.homeScores, null, 'fScores', { side: 'home' })
    add('awayScores', `${match.awayTeam} marca`, null, m.awayScores, null, 'fScores', { side: 'away' })
  }
  // Extra markets the collect stores (display only): goals on every line, by half, corners.
  const ex = match.oddsExtra || {}
  const lineOf = (group, key, line, text, kind, base = {}) => {
    const l = group?.[line]
    if (!l) return
    const f = fair2(l.over, l.under)
    add(`${key}o${line}`, `Más de ${line} ${text}`, f, null, l.over, kind, { ...base, line: +line, pick: 'mas' })
    add(`${key}u${line}`, `Menos de ${line} ${text}`, f == null ? null : 1 - f, null, l.under, kind, { ...base, line: +line, pick: 'menos' })
  }
  for (const line of ['0.5', '4.5']) lineOf(ex.goals, 'g', line, 'goles', 'fGoals')
  for (const line of ['0.5', '1.5']) lineOf(ex.firstHalf, 'h1', line, 'goles en el 1T', 'fHalf', { half: 1 })
  for (const line of ['0.5', '1.5']) lineOf(ex.secondHalf, 'h2', line, 'goles en el 2T', 'fHalf', { half: 2 })
  for (const line of Object.keys(ex.corners || {})) lineOf(ex.corners, 'c', line, 'córners', 'fCorners')
  if (om.btts) {
    const b = fair2(om.btts.yes, om.btts.no)
    add('bttsY', 'Ambos anotan', b, m ? m.btts : null, om.btts.yes, 'fBtts', { pick: 'si' })
    add('bttsN', 'No anotan ambos', b == null ? null : 1 - b, m ? 1 - m.btts : null, om.btts.no, 'fBtts', { pick: 'no' })
  } else if (m) {
    add('bttsY', 'Ambos anotan', null, m.btts, null, 'fBtts', { pick: 'si' })
    add('bttsN', 'No anotan ambos', null, 1 - m.btts, null, 'fBtts', { pick: 'no' })
  }
  const mw = om.matchWinner
  let ph, pd, pa
  const fromHouse = !!(mw && mw.home > 1 && mw.draw > 1 && mw.away > 1)
  if (fromHouse) {
    const s = 1 / mw.home + 1 / mw.draw + 1 / mw.away
    ph = 1 / mw.home / s; pd = 1 / mw.draw / s; pa = 1 / mw.away / s
  } else if (m) { ph = m.home; pd = m.draw; pa = m.away }
  if (ph != null) {
    const dc = (key, text, p) => out.push({ key, text, prob: p, source: fromHouse ? 'casa' : 'modelo', odds: ex.doubleChance?.[key] || (key === '1' ? mw?.home : key === '2' ? mw?.away : null) || null, kind: 'fResult', selector: { pick: key } })
    dc('1X', `Doble oportunidad: ${match.homeTeam} o empate`, ph + pd)
    dc('X2', `Doble oportunidad: ${match.awayTeam} o empate`, pa + pd)
    dc('12', 'Doble oportunidad: no hay empate', ph + pa)
    dc('1', `Gana ${match.homeTeam}`, ph)
    dc('2', `Gana ${match.awayTeam}`, pa)
  }
  const seen = new Map()
  for (const p of out) {                       // the same text can come from the house and the model: keep the house
    const q = seen.get(p.text)
    if (!q || (q.source !== 'casa' && p.source === 'casa')) seen.set(p.text, p)
  }
  return [...seen.values()].filter((p) => p.prob >= 0.5).sort((x, y) => y.prob - x.prob)
}

const MIN_ODDS = 1.1   // below this the pick pays nothing worth the risk (same floor as tennis)

// "Apuesta del día": of the matches not yet started today (else the next day with matches), the most likely
// pick that the house really prices (odds >= MIN_ODDS, source "casa"). Most likely, not best value.
export function pickOfDay(matches, nowBogota) {
  const upcoming = matches
    .filter((m) => m.status === 'SCHEDULED' && `${m.eventDate} ${m.eventTime}` > nowBogota)
    .sort((a, b) => `${a.eventDate} ${a.eventTime}`.localeCompare(`${b.eventDate} ${b.eventTime}`))
  if (!upcoming.length) return null
  const day = upcoming[0].eventDate
  let best = null
  for (const m of upcoming.filter((x) => x.eventDate === day)) {
    for (const p of likelyPicks(m)) {
      if (p.source !== 'casa' || !p.odds || p.odds < MIN_ODDS) continue
      if (!best || p.prob > best.pick.prob) best = { match: m, pick: p }
    }
  }
  return best ? { ...best, day } : null
}

// Conservative mode (football): the same idea as the tennis one, with numbers only. Per match not yet started,
// the most likely pick the house really prices (odds >= MIN_ODDS); "safe" from 75%, "very safe" from 85%.
// Combos: pairs of different matches by the chance that both come in. No measured edge behind any of it.
export const SAFE = 0.75
export const VERY_SAFE = 0.85
export const MAX_COMBOS = 5

export function conservativeModes(matches, nowBogota) {
  const upcoming = matches.filter((m) => m.status === 'SCHEDULED' && `${m.eventDate} ${m.eventTime}` > nowBogota)
  const singles = []
  for (const m of upcoming) {
    const best = likelyPicks(m).filter((p) => p.source === 'casa' && p.odds && p.odds >= MIN_ODDS && p.prob >= SAFE)[0]
    if (best) singles.push({ match: m, pick: best, level: best.prob >= VERY_SAFE ? 'muy segura' : 'segura' })
  }
  singles.sort((a, b) => b.pick.prob - a.pick.prob)
  const combos = []
  for (let i = 0; i < singles.length; i++) {
    for (let j = i + 1; j < singles.length; j++) {
      const a = singles[i], b = singles[j]
      combos.push({ legs: [a, b], prob: a.pick.prob * b.pick.prob, odds: a.pick.odds * b.pick.odds })
    }
  }
  combos.sort((x, y) => y.prob - x.prob)
  return { singles, combos: combos.slice(0, MAX_COMBOS) }
}
