<template>
  <!-- Football match card. Own component: the tennis card (MatchCard) is not shared on purpose. -->
  <div class="rounded-lg border border-slate-200 bg-white p-3 text-sm">
    <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
      <span>{{ match.league }} · {{ match.eventDate }} {{ match.eventTime }}</span>
      <span v-if="match.status === 'FINISHED'" class="rounded bg-slate-100 px-2 py-0.5 font-medium text-slate-700">Final</span>
      <span v-else-if="match.status === 'LIVE'" class="rounded bg-red-50 px-2 py-0.5 font-medium text-red-700">En vivo</span>
    </div>
    <div class="mt-1 flex items-center justify-between gap-3 text-base font-semibold text-slate-900">
      <span>{{ match.homeTeam }}</span>
      <span v-if="match.homeScore != null" class="tabular-nums">{{ match.homeScore }} - {{ match.awayScore }}</span>
      <span v-else class="text-slate-400">vs</span>
      <span class="text-right">{{ match.awayTeam }}</span>
    </div>

    <div v-if="price" class="mt-2 rounded border border-emerald-200 bg-emerald-50 px-2.5 py-2 text-xs text-slate-800">
      <div class="font-medium text-emerald-800">Goles · cuota de la casa</div>
      <div>
        Más de 2.5 a <b>{{ price.over }}</b> ({{ price.overPct }}%) · Menos de 2.5 a <b>{{ price.under }}</b> ({{ price.underPct }}%)
        <span v-if="price.bttsYes"> · Ambos anotan {{ price.bttsYes }} / {{ price.bttsNo }}</span>
      </div>
    </div>

    <div v-if="picks.length" class="mt-2 space-y-1">
      <div v-for="p in picks" :key="p.market" class="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span><span class="text-slate-500">{{ MARKET[p.market] || p.market }}:</span> <b class="text-slate-900">{{ p.prediction }}</b></span>
        <span class="flex items-center gap-2">
          <span class="text-slate-600">modelo {{ p.confidence }}%<template v-if="p.marketProbability != null"> · casa {{ Math.round(p.marketProbability * 100) }}%</template></span>
          <span class="rounded px-1.5 py-0.5 font-medium" :class="label(p).cls" :title="`Edge ${fmt(p.betEdge)} contra la cuota`">{{ label(p).text }}</span>
        </span>
      </div>
    </div>
    <p v-else-if="match.status === 'SCHEDULED'" class="mt-2 text-xs text-slate-500">Sin predicción todavía.</p>

    <details v-if="goalsRows.length" class="mt-2 rounded border border-slate-200">
      <summary class="cursor-pointer px-2.5 py-1.5 text-xs font-medium text-slate-800">
        Goles de cada equipo <span class="font-normal text-slate-500">· {{ goalsHint }}</span>
      </summary>
      <div class="space-y-1 border-t border-slate-100 px-2.5 py-2 text-xs text-slate-700">
        <div v-for="r in goalsRows" :key="r.team">
          <span class="font-medium">{{ r.team }}:</span>
          {{ r.goalsFor }} a favor y {{ r.goalsAgainst }} en contra por partido; más de 2.5 en {{ r.over25 }}% y ambos anotan en {{ r.btts }}% (últimos {{ r.n }})
          <div v-for="n in r.notes" :key="n" class="text-amber-800">» {{ n }}</div>
        </div>
        <p class="text-slate-500">Hay equipos que reciben y marcan en casi todos sus partidos. Es información, no está medida contra la cuota.</p>
      </div>
    </details>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { betEdge, edgeLabel, formatEdge } from '../utils/edge.js'

const props = defineProps({
  match: { type: Object, required: true },
  predictions: { type: Array, default: () => [] }
})

const MARKET = { 'Match Winner': 'Ganador', 'Over/Under 2.5 Goals': 'Goles', 'Both Teams To Score': 'Ambos anotan' }
const ORDER = ['Over/Under 2.5 Goals', 'Both Teams To Score', 'Match Winner']

const picks = computed(() => [...props.predictions].sort((a, b) => ORDER.indexOf(a.market) - ORDER.indexOf(b.market)))
const label = (p) => edgeLabel(betEdge(p))
const fmt = (e) => (e == null ? 'sin cuota' : formatEdge(e))

const price = computed(() => {
  const m = props.match.oddsMarkets
  const ou = m?.overUnder?.['2.5']
  if (!ou) return null
  const fair = 1 / ou.over / (1 / ou.over + 1 / ou.under)
  return {
    over: ou.over.toFixed(2), under: ou.under.toFixed(2),
    overPct: Math.round(fair * 100), underPct: Math.round((1 - fair) * 100),
    bttsYes: m.btts?.yes?.toFixed(2), bttsNo: m.btts?.no?.toFixed(2)
  }
})

const goalsRows = computed(() => {
  const t = props.match.goalsTrend
  if (!t) return []
  return [[props.match.homeTeam, t.home], [props.match.awayTeam, t.away]].filter(([, x]) => x).map(([team, x]) => ({
    team, n: x.n, goalsFor: x.goalsFor, goalsAgainst: x.goalsAgainst,
    over25: Math.round(x.over25 * 100), btts: Math.round(x.btts * 100), notes: x.notes || []
  }))
})
const goalsHint = computed(() => {
  const b = props.match.goalsTrend?.both
  return b ? `~${b.goals} goles por partido` : ''
})
</script>
