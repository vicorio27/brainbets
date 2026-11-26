<template>
  <section class="rounded-lg border border-emerald-200 bg-emerald-50/40 p-3">
    <h3 class="mb-1 text-sm font-semibold text-slate-800">Jugar el partido antes de que empiece</h3>
    <p class="mb-2 text-slate-600">
      Cada punto se sortea con la probabilidad de ganar un punto al saque de cada jugador
      ({{ names[0] }} {{ pct(pa) }}% · {{ names[1] }} {{ pct(pb) }}%). Al mejor de {{ bestOf }}.
    </p>

    <div class="overflow-x-auto" tabindex="0">
      <table class="w-full min-w-[20rem] text-left tabular-nums">
        <thead class="text-slate-500">
          <tr><th class="py-1 pr-2 font-medium">Jugador</th><th v-for="(s, i) in shownSets" :key="i" class="px-2 font-medium">Set {{ i + 1 }}</th><th class="px-2 font-medium">Juego</th></tr>
        </thead>
        <tbody>
          <tr v-for="k in [0, 1]" :key="k" class="border-t border-emerald-100">
            <td class="py-1 pr-2 font-medium" :class="m.winner === k ? 'text-emerald-800' : ''">
              <span v-if="!m.over && server === k" title="saca">● </span>{{ names[k] }}
            </td>
            <td v-for="(s, i) in shownSets" :key="i" class="px-2">{{ s[k] }}</td>
            <td class="px-2 font-semibold">{{ gameCell(k) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="m.over" class="mt-1 font-semibold text-emerald-800">Ganó {{ names[m.winner] }} {{ m.setsWon[m.winner] }}-{{ m.setsWon[1 - m.winner] }}.</p>
    <p v-else-if="m.tb" class="mt-1 text-slate-600">Tiebreak (a 7). Marcador de puntos arriba.</p>

    <div class="mt-2 flex flex-wrap gap-2">
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || auto" @click="step('point')">Punto</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || auto" @click="step('game')">Juego</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || auto" @click="step('set')">Set</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || auto" @click="step('match')">Partido</button>
      <button class="rounded border border-emerald-700 px-2 py-1 text-emerald-800 disabled:opacity-40" :disabled="m.over" @click="toggleAuto">{{ auto ? 'Pausar' : 'Auto' }}</button>
      <button class="rounded border border-slate-300 px-2 py-1 text-slate-700" @click="reset">Reiniciar</button>
    </div>

    <ul class="mt-2 max-h-40 space-y-0.5 overflow-y-auto" aria-live="polite">
      <li v-for="(e, i) in log" :key="i" :class="e.event ? 'font-medium text-slate-900' : 'text-slate-600'">{{ e.text }}</li>
      <li v-if="!log.length" class="text-slate-500">Aún no se ha jugado ningún punto.</li>
    </ul>

    <div class="mt-3 border-t border-emerald-100 pt-2">
      <button class="rounded border border-emerald-700 px-2 py-1 text-emerald-800" @click="runMany">Jugarlo 2.000 veces</button>
      <p v-if="mc" class="mt-1">
        En {{ mc.n }} partidos simulados: gana {{ names[0] }} <b>{{ pct(mc.p1) }}%</b> · {{ names[1] }} <b>{{ pct(1 - mc.p1) }}%</b>;
        {{ mc.games.toFixed(1) }} games, tiebreak {{ pct(mc.tiebreak) }}%, set decisivo {{ pct(mc.decider) }}%.
        Marcadores:
        <span v-for="s in mc.scores.slice(0, 4)" :key="s.score" class="mr-2 whitespace-nowrap"><b>{{ s.score }}</b> ({{ pct(s.p) }}%)</span>
      </p>
    </div>
    <p class="mt-2 text-slate-500">
      Un partido jugado es una sola tirada de dados: puede salir muy lejos de lo probable. No hay impulso, nervios ni cansancio,
      el modelo no ha ganado a la cuota y quién saca primero se sortea. Es para ver cómo puede ir, no una señal de apuesta.
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { monteCarlo, newMatch, playPoint, pointText, serverNow } from '../utils/tennisSim.js'

const props = defineProps({
  names: { type: Array, required: true },
  pa: { type: Number, required: true },
  pb: { type: Number, required: true },
  bestOf: { type: Number, default: 3 }
})
const pct = (x) => Math.round((x ?? 0) * 100)
const m = reactive(newMatch(props.bestOf))
const log = ref([])
const mc = ref(null)
const auto = ref(false)
let timer = null

const server = computed(() => serverNow(m))
const shownSets = computed(() => (m.over ? m.sets : [...m.sets, m.cur]))

function gameCell(k) {
  if (m.over) return ''
  if (m.tb) return m.pts[k]
  const [a, b] = m.pts
  const L = ['0', '15', '30', '40']
  if (a >= 3 && b >= 3) return a === b ? '40' : (m.pts[k] > m.pts[1 - k] ? 'Ad' : '40')
  return L[Math.min(m.pts[k], 3)]
}

function describe(r, before) {
  const who = props.names[r.winner]
  const ev = { point: '', game: ` · juego para ${who}`, break: ` · ¡BREAK de ${who}!`, set: ` · set para ${who}`, match: ` · partido para ${who}` }[r.event || 'point']
  const score = r.event ? `${m.sets.length ? m.sets.map((s) => s.join('-')).join(' ') : ''}` : pointText(m)
  return { event: r.event, text: `${props.names[r.server]} saca: punto de ${who}${ev}${r.event ? '' : ' → ' + score}` }
}

function one() {
  const r = playPoint(m, props.pa, props.pb)
  if (r) { log.value.unshift(describe(r)); if (log.value.length > 200) log.value.pop() }
  return r
}

function step(kind) {
  let guard = 0
  while (!m.over && guard++ < 5000) {
    const r = one()
    if (kind === 'point') break
    if (kind === 'game' && r.event) break
    if (kind === 'set' && (r.event === 'set' || r.event === 'match')) break
  }
}

function toggleAuto() {
  auto.value = !auto.value
  clearInterval(timer)
  if (auto.value) timer = setInterval(() => { one(); if (m.over) { auto.value = false; clearInterval(timer) } }, 350)
}

function reset() {
  clearInterval(timer)
  auto.value = false
  Object.assign(m, newMatch(props.bestOf))
  log.value = []
}

function runMany() { mc.value = monteCarlo(props.bestOf, props.pa, props.pb, 2000) }
onBeforeUnmount(() => clearInterval(timer))
</script>
