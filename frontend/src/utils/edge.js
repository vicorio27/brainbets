// One place for "what edge do we show for a prediction".
//
// The edge to act on is the market-anchored one (`betEdge`: the model's
// probability blended with the bookmaker's, see market_anchor_service on the
// backend). The model's own edge is kept for reference, and flagged when it
// is implausibly large: historically a 20%+ model edge has been the model
// disagreeing with a market that was right, not hidden value.
export const SUSPICIOUS_EDGE = 0.2

// The model alone: calibrated, except Exact Set Score (its confidence is not
// a binary pick, so the calibration curve does not apply).
export function modelEdge(p) {
  if (!p) return null
  if (p.market === 'Exact Set Score') return p.expectedValue ?? null
  return p.calibratedExpectedValue ?? p.expectedValue ?? null
}

export function betEdge(p) {
  if (!p) return null
  return p.betEdge ?? modelEdge(p)
}

export function betProbability(p) {
  if (!p) return null
  if (p.betProbability != null) return p.betProbability
  const c = p.market === 'Exact Set Score' ? p.confidence : (p.calibratedConfidence ?? p.confidence)
  return c != null ? c / 100 : null
}

// Full Kelly fraction for the anchored probability (0 when there is no edge).
// Falls back to the engine's own Kelly when the pick has no market anchor.
export function betKelly(p) {
  if (!p) return null
  if (p.betEdge == null || !p.betProbability) return p.kellyFraction ?? null
  const odds = (1 + p.betEdge) / p.betProbability
  return odds > 1 ? Math.max(0, p.betEdge / (odds - 1)) : 0
}

export function isSuspicious(edge) {
  return edge != null && edge > SUSPICIOUS_EDGE
}

// The pick has no market anchor and its only edge is an implausible one.
export function isSuspiciousPick(p) {
  return isSuspicious(betEdge(p)) || (p?.betEdge == null && isSuspicious(modelEdge(p)))
}

export function edgeBadgeClass(edge) {
  if (isSuspicious(edge)) return 'bg-amber-100 text-amber-800'
  if (edge >= 0.05) return 'bg-green-100 text-green-800'
  if (edge >= 0) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

// Plain-language verdict for lists. The number stays in the tooltip and in
// the prediction detail: a column of small negative percentages read as
// "everything is broken" when it only meant "no advantage over the house".
export function edgeLabel(edge) {
  if (edge == null) return { text: 'sin cuota', cls: 'bg-slate-100 text-slate-600' }
  if (isSuspicious(edge)) return { text: '⚠ dudoso', cls: 'bg-amber-100 text-amber-800' }
  if (edge >= 0.05) return { text: 'valor', cls: 'bg-green-100 text-green-800' }
  if (edge >= 0.02) return { text: 'valor leve', cls: 'bg-lime-100 text-lime-800' }
  return { text: 'sin valor', cls: 'bg-slate-100 text-slate-600' }
}

export function formatEdge(edge, digits = 1) {
  if (edge == null) return '–'
  const pct = edge * 100
  return (pct > 0 ? '+' : '') + pct.toFixed(digits) + '%'
}

// Tooltip / secondary line: how the shown edge was built.
export function edgeExplanation(p) {
  const parts = []
  const model = modelEdge(p)
  if (p?.betEdge != null) {
    parts.push(
      `Edge anclado a la cuota: ${formatEdge(p.betEdge)} (casa ${Math.round(p.marketProbability * 100)}%, modelo ${Math.round(p.modelProbability * 100)}%, peso del modelo ${Math.round((p.modelWeight ?? 0) * 100)}%)`
    )
    if (model != null) parts.push(`Edge del modelo solo: ${formatEdge(model)}`)
  } else if (model != null) {
    parts.push(`Edge del modelo: ${formatEdge(model)} (sin cuota de referencia para anclar)`)
  }
  if (isSuspicious(model)) parts.push('Un edge del modelo mayor a 20% suele ser el modelo equivocándose contra el mercado')
  return parts.join(' | ')
}
