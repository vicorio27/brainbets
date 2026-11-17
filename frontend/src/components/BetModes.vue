<template>
  <section class="mb-6 rounded-lg border border-slate-200 bg-white p-4" aria-label="Apuestas por modo">
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <h2 class="text-lg font-semibold text-slate-900 mr-2">¿Cómo quieres apostar?</h2>
      <div class="inline-flex rounded-lg border border-slate-300 overflow-hidden" role="group" aria-label="Modo">
        <button v-for="m in MODES" :key="m.key" type="button"
          class="px-3 py-1.5 text-sm font-medium"
          :class="mode === m.key ? m.on : 'bg-white text-slate-700 hover:bg-slate-50'"
          :aria-pressed="mode === m.key" @click="setMode(m.key)">{{ m.label }}</button>
      </div>
      <div v-if="mode === 'conservadora'" class="inline-flex rounded-lg border border-slate-300 overflow-hidden" role="group" aria-label="Tipo de apuesta">
        <button v-for="t in TYPES" :key="t.key" type="button"
          class="px-3 py-1.5 text-sm font-medium"
          :class="type === t.key ? 'bg-slate-800 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'"
          :aria-pressed="type === t.key" @click="setType(t.key)">{{ t.label }}</button>
      </div>
    </div>

    <p v-if="loading" class="text-sm text-slate-500">Cargando…</p>

    <!-- Conservative -->
    <template v-else-if="mode === 'conservadora'">
      <p class="text-sm text-slate-600 mb-3">
        Lo más seguro de cada partido según la casa (al menos un set, favorito claro). Si los datos respaldan al no favorito,
        su versión segura: que gane al menos un set. Paga poco; se gana seguido.
      </p>
      <template v-if="type === 'individual'">
        <p v-if="!modes.conservative.singles.length" class="text-sm text-slate-500">No hay apuestas seguras con cuota en los partidos por jugar.</p>
        <ul v-else class="divide-y divide-slate-100">
          <li v-for="s in modes.conservative.singles" :key="s.matchId + s.label" class="py-2 flex items-start gap-3">
            <button type="button" class="mt-0.5 shrink-0 w-7 h-7 rounded-full border text-sm font-bold"
              :class="combo.has(key(s)) ? 'bg-emerald-600 text-white border-emerald-600' : 'border-emerald-600 text-emerald-700 hover:bg-emerald-50'"
              :aria-label="combo.has(key(s)) ? 'Quitar de mi combinada' : 'Agregar a mi combinada'"
              @click="toggle(s)">{{ combo.has(key(s)) ? '✓' : '+' }}</button>
            <div class="min-w-0 flex-1">
              <div class="font-medium text-slate-900">{{ s.label }}
                <span class="ml-1 inline-flex px-1.5 rounded text-xs font-medium" :class="levelClass[s.level]">{{ s.level }}</span>
              </div>
              <div class="text-xs text-slate-500">{{ s.match }} · {{ when(s) }}<span v-if="s.tournament"> · {{ s.tournament }}</span></div>
              <div v-if="s.backed" class="text-xs text-slate-700 mt-0.5">{{ s.why }}</div>
            </div>
            <div class="text-right shrink-0">
              <div class="font-semibold text-slate-900">{{ pct(s.probability) }}%</div>
              <div class="text-xs text-slate-600">cuota {{ s.odds.toFixed(2) }}<span v-if="s.oddsKind === 'aprox'"> ≈</span></div>
            </div>
          </li>
        </ul>
      </template>
      <template v-else>
        <p v-if="!modes.conservative.combos.length" class="text-sm text-slate-500">Hacen falta al menos dos partidos con apuesta segura.</p>
        <ul v-else class="space-y-2">
          <li v-for="(c, i) in modes.conservative.combos" :key="i" class="rounded border border-slate-200 p-3">
            <div class="flex items-start justify-between gap-3">
              <ul class="text-sm space-y-1 min-w-0">
                <li v-for="l in c.legs" :key="l.matchId">
                  <span class="font-medium text-slate-900">{{ l.label }}</span>
                  <span class="text-slate-600"> · {{ pct(l.probability) }}% · {{ l.odds.toFixed(2) }}</span>
                  <div class="text-xs text-slate-500">{{ l.match }} · {{ when(l) }}</div>
                </li>
              </ul>
              <div class="text-right shrink-0">
                <div class="font-semibold text-slate-900">{{ pct(c.probability) }}%</div>
                <div class="text-xs text-slate-600">cuota {{ c.odds.toFixed(2) }}</div>
                <button type="button" class="mt-1 px-2 py-1 rounded bg-emerald-700 text-white text-xs font-medium hover:bg-emerald-800" @click="useCombo(c)">Usar esta</button>
              </div>
            </div>
          </li>
        </ul>
        <p class="text-xs text-slate-500 mt-2">Probabilidad de que salgan las dos según la casa, sin margen. Al pulsar "Usar esta" reemplaza tu combinada y la puedes registrar abajo.</p>
      </template>
    </template>

    <!-- Risky -->
    <template v-else>
      <p class="text-sm text-slate-600 mb-3">
        El no favorito apostado directo, solo cuando hay argumentos claros del historial (cara a cara, forma, cansancio, noticias).
        Un buen precio por sí solo no cuenta. Paga mucho; se pierde seguido.
      </p>
      <p v-if="!modes.risky.length" class="text-sm text-slate-500">Hoy ningún no favorito tiene argumentos claros.</p>
      <ul v-else class="space-y-2">
        <li v-for="r in modes.risky" :key="r.matchId" class="rounded border border-amber-200 bg-amber-50 p-3">
          <div class="flex items-start gap-3">
            <button type="button" class="mt-0.5 shrink-0 w-7 h-7 rounded-full border text-sm font-bold"
              :class="combo.has(key(r)) ? 'bg-amber-600 text-white border-amber-600' : 'border-amber-600 text-amber-800 hover:bg-amber-100'"
              :aria-label="combo.has(key(r)) ? 'Quitar de mi combinada' : 'Agregar a mi combinada'"
              @click="toggle(r)">{{ combo.has(key(r)) ? '✓' : '+' }}</button>
            <div class="min-w-0 flex-1">
              <div class="font-medium text-slate-900">{{ r.label }}</div>
              <div class="text-xs text-slate-500">{{ r.match }} · {{ when(r) }}</div>
              <ul class="mt-1 text-sm text-slate-700 list-disc pl-5">
                <li v-for="x in r.reasons" :key="x.text" :title="x.evidence">{{ x.text }}</li>
              </ul>
              <p v-if="r.safeVersion" class="mt-1 text-xs text-emerald-800">
                Versión conservadora: {{ r.safeVersion.label }} · {{ pct(r.safeVersion.probability) }}% · {{ r.safeVersion.odds.toFixed(2) }}
              </p>
              <p class="mt-1 text-xs text-slate-500">{{ r.note }}</p>
            </div>
            <div class="text-right shrink-0">
              <div class="font-semibold text-slate-900">{{ pct(r.probability) }}%</div>
              <div class="text-xs text-slate-600">cuota {{ r.odds.toFixed(2) }}</div>
            </div>
          </div>
        </li>
      </ul>
    </template>

    <p v-if="clash" class="mt-2 text-xs text-amber-800">Ya tienes «{{ clash.label }}» de ese partido en tu combinada: solo una por partido.</p>
    <div v-if="combo.count" class="mt-4"><ComboPanel /></div>

    <!-- Odds movement and bargains -->
    <details class="mt-4 text-sm">
      <summary class="cursor-pointer font-medium text-slate-900">📈 Movimiento de cuotas y gangas</summary>
      <p class="text-xs text-slate-500 mt-1">
        Cómo se movió la cuota de cada partido entre recolecciones (03:00, 12:00 y 20:00), desde el 17-nov.
        Que suba la probabilidad de un jugador = el dinero entra a su favor.
      </p>
      <p v-if="!movingMatches.length" class="mt-2 text-slate-500">Todavía no hay movimientos: hace falta al menos una recolección más desde que se guarda la cuota.</p>
      <div v-for="m in movingMatches" :key="m.matchId" class="mt-2">
        <div class="font-medium text-slate-800">{{ m.match }} <span class="text-xs text-slate-500">({{ m.snapshots }} fotos)</span></div>
        <ul class="text-xs">
          <li v-for="x in m.moves" :key="x.market + x.side" :class="x.moved ? 'font-medium' : 'text-slate-500'">
            {{ x.label }}: {{ x.fromOdds }} → {{ x.toOdds }}
            <span :class="x.delta > 0 ? 'text-emerald-700' : x.delta < 0 ? 'text-red-700' : ''">({{ x.delta > 0 ? '+' : '' }}{{ (x.delta * 100).toFixed(1) }} puntos)</span>
          </li>
        </ul>
      </div>
      <p class="mt-3 font-medium text-slate-900">Gangas: una casa paga por encima de la cuota justa</p>
      <p v-if="!movement.bargains.length" class="text-slate-500">Ninguna ahora.</p>
      <ul v-else class="text-xs space-y-0.5 mt-1">
        <li v-for="b in movement.bargains" :key="b.matchId + b.market + b.pick">
          <span class="font-medium">{{ b.pick }}</span> {{ b.market === 'Set 1 Winner' ? 'gana el 1er set' : 'gana el partido' }}
          ({{ b.home }} vs {{ b.away }}): {{ b.bestOdds.toFixed(2) }} en {{ b.bestBook || 'referencia' }}, justa {{ (1 / b.fairProbability).toFixed(2) }},
          {{ pct(b.fairProbability) }}% · +{{ (b.edge * 100).toFixed(1) }}%
          <span v-if="b.level === 'check'" class="text-amber-800">· confirma la cuota</span>
        </li>
      </ul>
      <p class="text-xs text-slate-500 mt-1">
        Ojo: medido sobre lo ya jugado, las "gangas" grandes casi siempre eran precios viejos de una casa y perdieron. Una ganga no hace segura una apuesta.
      </p>
    </details>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../stores/api.js'
import { useComboStore, legKey } from '../stores/combo.js'
import ComboPanel from './ComboPanel.vue'

const MODES = [
  { key: 'conservadora', label: 'Conservadora', on: 'bg-emerald-700 text-white' },
  { key: 'arriesgada', label: 'Arriesgada', on: 'bg-amber-600 text-white' }
]
const TYPES = [
  { key: 'individual', label: 'Individual' },
  { key: 'combinada', label: 'Combinada' }
]
const levelClass = {
  'muy segura': 'bg-emerald-100 text-emerald-800',
  segura: 'bg-sky-100 text-sky-800',
  'con argumentos': 'bg-amber-100 text-amber-900'
}

const combo = useComboStore()
const mode = ref('conservadora')   // always starts conservative
const type = ref(readType())
const loading = ref(true)
const modes = ref({ conservative: { singles: [], combos: [] }, risky: [] })
const movement = ref({ matches: [], bargains: [] })
const clash = ref(null)

function readType() {
  try { return localStorage.getItem('brainbets.betType') === 'combinada' ? 'combinada' : 'individual' } catch (e) { return 'individual' }
}
function setMode(m) { mode.value = m; clash.value = null }
function setType(t) {
  type.value = t
  try { localStorage.setItem('brainbets.betType', t) } catch (e) { /* not saved, fine */ }
}
const pct = (p) => (p == null ? '-' : Math.round(p * 100))
const when = (x) => [x.eventDate, x.eventTime].filter(Boolean).join(' ')
const key = (x) => legKey(x.matchId, x.label)
function leg(x) {
  return {
    key: key(x), matchId: x.matchId, match: x.match, eventDate: x.eventDate, eventTime: x.eventTime,
    label: x.label, kind: x.kind, selector: x.selector, probability: x.probability, odds: x.odds,
    oddsKind: x.oddsKind || 'directa', bestOdds: x.bestOdds || x.odds, bestBook: x.bestBook || null, bestNeedsCheck: false
  }
}
function toggle(x) {
  clash.value = null
  if (combo.has(key(x))) { combo.remove(key(x)); return }
  const current = combo.add(leg(x))
  if (current) clash.value = current
}
function useCombo(c) {
  combo.clear()
  c.legs.forEach((l) => combo.add(leg(l)))
}
const movingMatches = computed(() => (movement.value.matches || []).filter((m) => m.moves.length))

onMounted(async () => {
  try {
    const [a, b] = await Promise.all([api.get('/matches/bet-modes'), api.get('/matches/odds-movement')])
    modes.value = a.data
    movement.value = b.data
  } catch (e) {
    /* keep the empty state */
  } finally {
    loading.value = false
  }
})
</script>
