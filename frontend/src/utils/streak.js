// Tournament streak tags. Information only: on 27k ATP matches (2010-2020) the
// Pinnacle price already included these streaks (AGENTS.md, 2026-10-15).
export function streakTags(s) {
  if (!s || !s.wins) return []
  const tags = []
  if (s.wins >= 2) tags.push({
    key: 'wins',
    text: `🔥 ${s.wins} victorias en el torneo` + (s.upsets && !s.lastUpset ? ` (${s.upsets} como no favorito)` : ''),
    cls: 'bg-orange-100 text-orange-800',
    title: 'Ya ganó en este torneo. En 2010-2020, los no favoritos con 2 o más victorias en el torneo ganaron 29.3% contra 29.2% que daba la cuota: la casa ya lo tiene en el precio.'
  })
  if (s.lastUpset) {
    tags.push({
      key: 'upset',
      text: '⚡ viene de dar la sorpresa',
      cls: 'bg-violet-100 text-violet-800',
      title: 'Ganó su partido anterior siendo no favorito. En 2010-2020 el siguiente partido lo ganaron 32.9% contra 34.6% que daba la cuota (en 2018-2020 ya no se notaba); apostarle al rival dejó 0.0%.'
    })
  }
  if (s.lowRankRun) {
    tags.push({
      key: 'lowrank',
      text: '⚠ ranking +100 en racha',
      cls: 'bg-amber-100 text-amber-800',
      title: 'Ranking peor que 100 y 2 o más victorias en el torneo. En 2010-2020 ganaron 26.7% contra 27.5% que daba la cuota: el mercado los sobrevalora un poco, pero apostarle al rival tampoco dejó ganancia (-2.1%).'
    })
  }
  return tags
}
