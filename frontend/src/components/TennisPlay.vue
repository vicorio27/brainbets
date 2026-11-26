<template>
  <section class="rounded-lg border border-emerald-200 bg-emerald-50/40 p-3">
    <h3 class="mb-1 text-sm font-semibold text-slate-800">{{ start ? 'Jugar el resto del partido desde el marcador real' : 'Jugar el partido antes de que empiece' }}</h3>
    <p class="mb-2 text-slate-600">
      Quién gana cada punto lo sortea el modelo con la probabilidad de ganar un punto al saque de cada uno
      ({{ names[0] }} {{ pct(pa) }}% · {{ names[1] }} {{ pct(pb) }}%), al mejor de {{ bestOf }}.
      <template v-if="start">Parte del marcador real de ahora: lo que pase aquí es una simulación, no lo que va a pasar.</template>
      La bola de la cancha es solo para verlo: cuántos golpes tuvo el punto y cómo acabó se dibuja al azar y no aporta información.
    </p>

    <TennisCourt ref="court" :names="names" :share="share" :window-size="WINDOW" :speed="speed" />

    <div class="mt-2 overflow-x-auto" tabindex="0">
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
    <p v-else-if="m.tb" class="mt-1 text-slate-600">Tiebreak (a 7).</p>

    <div class="mt-2 flex flex-wrap items-center gap-2">
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || busy || auto" @click="step('point')">Punto</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || busy || auto" @click="step('game')">Juego</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || busy || auto" @click="step('set')">Set</button>
      <button class="rounded bg-emerald-700 px-2 py-1 text-white disabled:opacity-40" :disabled="m.over || busy || auto" @click="step('match')">Partido</button>
      <button class="rounded border border-emerald-700 px-2 py-1 text-emerald-800 disabled:opacity-40" :disabled="m.over" @click="toggleAuto">{{ auto ? 'Pausar' : 'Auto' }}</button>
      <button class="rounded border border-slate-300 px-2 py-1 text-slate-700" @click="reset">{{ start ? 'Partir del marcador real' : 'Reiniciar' }}</button>
      <label class="ml-auto flex items-center gap-1 text-slate-600">Velocidad
        <select v-model.number="speed" class="rounded border border-slate-300 bg-white px-1 py-0.5" aria-label="Velocidad de la animación">
          <option :value="0.6">lenta</option><option :value="1">normal</option><option :value="2">rápida</option><option :value="4">turbo</option>
        </select>
      </label>
    </div>

    <div class="mt-2 overflow-x-auto" tabindex="0">
      <table class="w-full min-w-[20rem] text-left tabular-nums">
        <thead class="text-slate-500">
          <tr><th class="py-1 pr-2 font-medium">Hasta ahora</th><th class="px-2 font-medium">Puntos</th><th class="px-2 font-medium">Aces</th><th class="px-2 font-medium">Dobles faltas</th><th class="px-2 font-medium">Winners</th><th class="px-2 font-medium">Errores</th><th class="px-2 font-medium">Breaks</th></tr>
        </thead>
        <tbody>
          <tr v-for="k in [0, 1]" :key="k" class="border-t border-emerald-100">
            <td class="py-1 pr-2 font-medium">{{ names[k] }}</td>
            <td class="px-2">{{ tally.pts[k] }}</td><td class="px-2">{{ tally.aces[k] }}</td><td class="px-2">{{ tally.df[k] }}</td>
            <td class="px-2">{{ tally.winners[k] }}</td><td class="px-2">{{ tally.errors[k] }}</td><td class="px-2">{{ tally.breaks[k] }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="tally.points" class="mt-1 text-slate-500">Golpes por punto: {{ (tally.shots / tally.points).toFixed(1) }} de media · el más largo, {{ tally.longest }}. Aces, winners y errores son del dibujo, no del modelo.</p>
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
      el modelo no ha ganado a la cuota y quién saca primero se sortea. El «quién manda» solo cuenta los últimos puntos ganados.
      Es para ver cómo puede ir, no una señal de apuesta.
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import TennisCourt from './TennisCourt.vue'
import { cloneMatch, monteCarlo, newMatch, playPoint, pointText, serverNow } from '../utils/tennisSim.js'
import { KIND_TEXT, makeRally } from '../utils/rally.js'

const props = defineProps({
  names: { type: Array, required: true },
  pa: { type: Number, required: true },
  pb: { type: Number, required: true },
  bestOf: { type: Number, default: 3 },
  start: { type: Object, default: null } // optional state to start from (live mode: the real score)
})
const WINDOW = 10
const pct = (x) => Math.round((x ?? 0) * 100)
const fresh = () => (props.start ? cloneMatch(props.start) : newMatch(props.bestOf))
const m = reactive(fresh())
const log = ref([])
const mc = ref(null)
const auto = ref(false)
const busy = ref(false)
const speed = ref(1)
const court = ref(null)
const recent = ref([])
const blank = () => ({ pts: [0, 0], aces: [0, 0], df: [0, 0], winners: [0, 0], errors: [0, 0], breaks: [0, 0], points: 0, shots: 0, longest: 0 })
const tally = reactive(blank())
let run = 0

const server = computed(() => serverNow(m))
const shownSets = computed(() => (m.over ? m.sets : [...m.sets, m.cur]))
const share = computed(() => (recent.value.length ? recent.value.filter((w) => w === 0).length / recent.value.length : 0.5))

function gameCell(k) {
  if (m.over) return ''
  if (m.tb) return m.pts[k]
  const [a, b] = m.pts
  const L = ['0', '15', '30', '40']
  if (a >= 3 && b >= 3) return a === b ? '40' : m.pts[k] > m.pts[1 - k] ? 'Ad' : '40'
  return L[Math.min(m.pts[k], 3)]
}

function note(r, rally) {
  const who = props.names[r.winner]
  const loser = props.names[1 - r.winner]
  const how = { ace: `ace de ${who}`, doublefault: `doble falta de ${loser}`, winner: `winner de ${who}`, error: `error de ${loser}` }[rally.kind]
  const end = { game: ` · juego para ${who}`, break: ` · ¡BREAK de ${who}!`, set: ` · set para ${who}`, match: ` · partido para ${who}` }[r.event] || ''
  return `${props.names[r.server]} saca · ${how} (${rally.n} ${rally.n === 1 ? 'golpe' : 'golpes'})${end}${r.event ? '' : ' → ' + pointText(m)}`
}

function count(r, rally) {
  tally.pts[r.winner] += 1
  tally.points += 1
  tally.shots += rally.n
  tally.longest = Math.max(tally.longest, rally.n)
  if (rally.kind === 'ace') tally.aces[r.server] += 1
  else if (rally.kind === 'doublefault') tally.df[r.server] += 1
  else if (rally.kind === 'winner') tally.winners[r.winner] += 1
  else tally.errors[1 - r.winner] += 1
  if (r.event === 'break') tally.breaks[r.winner] += 1
  recent.value = [...recent.value.slice(-(WINDOW - 1)), r.winner]
}

// Decides the point (model) and draws a rally for it. Returns {r, rally} or null.
function decide() {
  const parity = m.pts[0] + m.pts[1]
  const r = playPoint(m, props.pa, props.pb)
  if (!r) return null
  const rally = makeRally(r, parity)
  count(r, rally)
  log.value.unshift({ event: r.event, text: note(r, rally) })
  if (log.value.length > 200) log.value.pop()
  return { r, rally }
}

async function show(x) {
  if (!x) return
  busy.value = true
  const my = run
  await court.value?.play(x.rally)
  if (my === run && x.r.event) {
    const t = { break: 'BREAK', game: 'JUEGO', set: 'SET', match: 'PARTIDO' }[x.r.event]
    court.value?.flash(`${t} ${props.names[x.r.winner]}`.toUpperCase().slice(0, 22), x.r.event === 'match' ? '#fde047' : '#7dd3fc')
    await new Promise((res) => setTimeout(res, 700 / speed.value))
  }
  if (my === run) busy.value = false
}

async function step(kind) {
  if (busy.value) return
  let x = null
  let guard = 0
  while (!m.over && guard++ < 5000) {
    x = decide()
    if (!x || kind === 'point') break
    if (kind === 'game' && x.r.event) break
    if (kind === 'set' && (x.r.event === 'set' || x.r.event === 'match')) break
  }
  await show(x) // only the last point is drawn when several are played at once
}

async function toggleAuto() {
  auto.value = !auto.value
  if (!auto.value) return
  const my = run
  while (auto.value && !m.over && my === run) {
    await show(decide())
  }
  if (my === run) auto.value = false
}

function reset() {
  run += 1
  auto.value = false
  busy.value = false
  Object.assign(m, fresh())
  Object.assign(tally, blank())
  recent.value = []
  log.value = []
  court.value?.reset()
}

function runMany() { mc.value = monteCarlo(props.bestOf, props.pa, props.pb, 2000, Math.random, props.start) }
onBeforeUnmount(() => { run += 1 })
void KIND_TEXT
</script>
