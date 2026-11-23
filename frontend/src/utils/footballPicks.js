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
  const add = (key, text, house, model, odds) => {
    const p = house ?? model
    if (p == null) return
    out.push({ key, text, prob: p, source: house != null ? 'casa' : 'modelo', odds: odds || null })
  }
  for (const line of ['1.5', '2.5', '3.5']) {
    const l = ou[line]
    if (!l) continue
    const o = fair2(l.over, l.under)
    const mk = m ? m['over' + line.replace('.', '')] : null
    add('o' + line, `Más de ${line} goles`, o, mk, l.over)
    add('u' + line, `Menos de ${line} goles`, o == null ? null : 1 - o, mk == null ? null : 1 - mk, l.under)
  }
  if (m) {
    add('o0.5', 'Más de 0.5 goles', null, m.over05)
    add('u4.5', 'Menos de 4.5 goles', null, 1 - m.over45)
    add('homeScores', `${match.homeTeam} marca`, null, m.homeScores)
    add('awayScores', `${match.awayTeam} marca`, null, m.awayScores)
  }
  if (om.btts) {
    const b = fair2(om.btts.yes, om.btts.no)
    add('bttsY', 'Ambos anotan', b, m ? m.btts : null, om.btts.yes)
    add('bttsN', 'No anotan ambos', b == null ? null : 1 - b, m ? 1 - m.btts : null, om.btts.no)
  } else if (m) {
    add('bttsY', 'Ambos anotan', null, m.btts)
    add('bttsN', 'No anotan ambos', null, 1 - m.btts)
  }
  const mw = om.matchWinner
  let ph, pd, pa
  const fromHouse = !!(mw && mw.home > 1 && mw.draw > 1 && mw.away > 1)
  if (fromHouse) {
    const s = 1 / mw.home + 1 / mw.draw + 1 / mw.away
    ph = 1 / mw.home / s; pd = 1 / mw.draw / s; pa = 1 / mw.away / s
  } else if (m) { ph = m.home; pd = m.draw; pa = m.away }
  if (ph != null) {
    const dc = (key, text, p) => out.push({ key, text, prob: p, source: fromHouse ? 'casa' : 'modelo', odds: null })
    dc('1X', `Doble oportunidad: ${match.homeTeam} o empate`, ph + pd)
    dc('X2', `Doble oportunidad: ${match.awayTeam} o empate`, pa + pd)
    dc('12', 'Doble oportunidad: no hay empate', ph + pa)
    dc('1', `Gana ${match.homeTeam}`, ph)
    dc('2', `Gana ${match.awayTeam}`, pa)
  }
  return out.filter((p) => p.prob >= 0.5).sort((x, y) => y.prob - x.prob)
}
