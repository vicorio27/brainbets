<template>
  <section class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/40 p-3 text-sm">
    <h2 class="text-sm font-semibold text-slate-900">Lo que pasa contra lo que simulamos</h2>
    <p class="mb-2 text-slate-600">
      El marcador real leído con el modelo de puntos de saque congelado antes del partido
      ({{ names[0] }} gana el {{ pct(model.pa) }}% de sus puntos de saque · {{ names[1] }} el {{ pct(model.pb) }}%), al mejor de {{ model.bestOf }}.
    </p>

    <!-- who wins from the real score -->
    <div v-if="pLive != null">
      <div class="flex items-baseline justify-between gap-2">
        <div class="font-semibold text-slate-900"><span class="inline-block h-2.5 w-2.5 rounded-full align-baseline" :style="{ background: C1 }"></span> {{ names[0] }} <span class="text-lg tabular-nums">{{ pct(pLive) }}%</span></div>
        <div class="text-right font-semibold text-slate-900"><span class="text-lg tabular-nums">{{ pct(1 - pLive) }}%</span> {{ names[1] }} <span class="inline-block h-2.5 w-2.5 rounded-full align-baseline" :style="{ background: C2 }"></span></div>
      </div>
      <div class="relative mt-1 h-3 overflow-hidden rounded-full bg-slate-200" role="img" :aria-label="`Probabilidad de ganar el partido: ${names[0]} ${pct(pLive)}%, ${names[1]} ${pct(1 - pLive)}%`">
        <div class="h-full transition-all duration-700" :style="{ width: pct(pLive) + '%', background: C1 }"></div>
        <div class="absolute right-0 top-0 h-full transition-all duration-700" :style="{ width: pct(1 - pLive) + '%', background: C2 }"></div>
        <div class="absolute top-0 h-full w-0.5 bg-white/90" :style="{ left: pct(pre) + '%' }" title="Antes de empezar"></div>
      </div>
      <p class="mt-1 text-slate-700">
        <template v-if="state && state.m.over">Partido terminado.</template>
        <template v-else>Antes de empezar daba {{ pct(pre) }}% a {{ names[0] }} (la rayita blanca); con el marcador de ahora, {{ pct(pLive) }}%
          <b :class="pLive >= pre ? 'text-emerald-800' : 'text-rose-800'">({{ pLive >= pre ? '+' : '' }}{{ Math.round((pLive - pre) * 100) }} puntos)</b>.</template>
        <span v-if="state && state.serverGuessed" class="text-slate-500"> El feed no dice quién saca: se promedian los dos casos.</span>
      </p>
    </div>

    <div v-if="path && path.length > 2" class="mt-3">
      <h3 class="mb-1 font-semibold text-slate-800">Cómo se ha movido el partido</h3>
      <WinPathChart :path="path" :now="pLive" :names="names" />
    </div>

    <!-- real points on the court -->
    <div class="mt-3">
      <h3 class="mb-1 font-semibold text-slate-800">Los puntos reales en la cancha</h3>
      <TennisCourt ref="court" :names="names" :share="share" :window-size="10" :speed="1" />
      <p class="mt-1 text-xs text-slate-500">
        Cada punto nuevo del feed se dibuja aquí: quién lo ganó y si fue ace, doble falta, winner o error no forzado es real.
        El peloteo (cuántos golpes y dónde cae la bola) se dibuja al azar porque el feed no lo trae. La barra «quién manda» usa las últimas 10 bolas.
        Cuando entre dos lecturas (cada 30 s) se juega más de un punto, solo se anuncian.
      </p>
    </div>

    <!-- real against expected -->
    <div v-if="rve" class="mt-3">
      <h3 class="mb-1 font-semibold text-slate-800">Real contra lo esperado</h3>
      <div class="overflow-x-auto" tabindex="0">
        <table class="w-full min-w-[26rem] text-left tabular-nums">
          <thead class="text-slate-500">
            <tr><th class="py-1 pr-2 font-medium">Puntos de saque ganados</th><th class="px-2 font-medium">Real</th><th class="px-2 font-medium">Esperado</th><th class="px-2 font-medium">Margen por azar</th><th class="px-2 font-medium">Lectura</th></tr>
          </thead>
          <tbody>
            <tr v-for="(k, i) in ['p1', 'p2']" :key="k" class="border-t border-emerald-100">
              <td class="py-1 pr-2 font-medium">{{ names[i] }}</td>
              <td class="px-2">{{ rve[k].won }}/{{ rve[k].n }} · {{ pct(rve[k].rate) }}%</td>
              <td class="px-2">{{ pct(rve[k].expected) }}%</td>
              <td class="px-2">±{{ margin(rve[k]) }} pts</td>
              <td class="px-2" :class="LEVEL_CLASS[rve[k].level]">{{ LEVEL_TEXT[rve[k].level] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="mt-1 text-slate-700">
        Puntos totales hasta ahora: <b>{{ names[0] }} {{ rve.points.real[0] ?? '?' }}</b> – <b>{{ names[1] }} {{ rve.points.real[1] ?? '?' }}</b>;
        con esos saques, el modelo esperaba {{ Math.round(rve.points.expected[0]) }} – {{ Math.round(rve.points.expected[1]) }}.
      </p>
      <p class="text-xs text-slate-500">El margen por azar es el que se desvía un 95% de las veces un partido jugado tal como dice el modelo. Con pocos puntos, casi todo cabe ahí.</p>
    </div>

    <details v-if="state && !state.m.over" class="mt-3 rounded border border-emerald-200 bg-white/60 p-2" @toggle="openSim = $event.target.open">
      <summary class="cursor-pointer font-medium text-slate-800">Jugar el resto del partido desde este marcador</summary>
      <div v-if="openSim" class="mt-2">
        <TennisPlay :names="names" :pa="model.pa" :pb="model.pb" :best-of="model.bestOf" :start="state.m" />
      </div>
    </details>

    <p class="mt-2 text-xs text-slate-500">
      Modelo de puntos independientes: no hay impulso, nervios ni cansancio, y el tiebreak es a 7 en todo set. No le ganó a la cuota en 2.272 partidos
      y el plan no trae cuotas en vivo, así que esto describe el partido y no es una señal de apuesta.
      <span v-if="model.trust < 0.5"> Aviso: de estos jugadores hay pocos partidos con estadísticas de saque (fiabilidad {{ pct(model.trust) }}%), así que las probabilidades de saque son menos firmes.</span>
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import TennisCourt from './TennisCourt.vue'
import TennisPlay from './TennisPlay.vue'
import WinPathChart from './WinPathChart.vue'
import { makeRally } from '../utils/rally.js'
import { liveWinProb, newPoints, preMatchProb, realVsExpected, stateFromReading, winPath } from '../utils/liveSim.js'

const props = defineProps({ match: { type: Object, required: true } })
const C1 = '#f59e0b'
const C2 = '#ec4899'
const LEVEL_TEXT = { pronto: 'muy pronto', normal: 'dentro de lo esperado', alto: 'por encima', muy_alto: 'muy por encima', bajo: 'por debajo', muy_bajo: 'muy por debajo' }
const LEVEL_CLASS = {
  pronto: 'text-slate-500', normal: 'text-slate-700', alto: 'text-emerald-800', muy_alto: 'font-semibold text-emerald-800',
  bajo: 'text-rose-800', muy_bajo: 'font-semibold text-rose-800'
}
const pct = (x) => Math.round((x ?? 0) * 100)
const margin = (r) => (r.n ? Math.round(196 * Math.sqrt((r.expected * (1 - r.expected)) / r.n)) : 0)

const model = computed(() => props.match.model)
const reading = computed(() => props.match.reading)
const names = computed(() => [props.match.player1, props.match.player2])
const state = computed(() => stateFromReading(reading.value, model.value.bestOf))
const pLive = computed(() => liveWinProb(state.value, model.value.pa, model.value.pb))
const pre = computed(() => preMatchProb(model.value.bestOf, model.value.pa, model.value.pb))
const path = computed(() => {
  try {
    return winPath(reading.value?.pbp, model.value.bestOf, model.value.pa, model.value.pb, state.value)
  } catch (e) {
    return null
  }
})
const rve = computed(() => realVsExpected(reading.value, model.value.pa, model.value.pb))
const share = computed(() => {
  const a = reading.value?.stats?.p1?.last10
  const b = reading.value?.stats?.p2?.last10
  return a != null && b != null && a + b > 0 ? a / (a + b) : 0.5
})
const openSim = ref(false)

// ---- real points drawn on the court as they arrive ----
const court = ref(null)
let alive = true
let queue = Promise.resolve()
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const idx = (t) => (t === 'p1' ? 0 : t === 'p2' ? 1 : null)

async function animate(np, prev, cur) {
  if (!alive) return
  const server = idx(prev.server)
  if (np.n === 1 && server != null) {
    const before = stateFromReading(prev, model.value.bestOf)
    const parity = before ? before.m.pts[0] + before.m.pts[1] : 0
    await court.value?.play(makeRally({ server, winner: np.winner }, parity, Math.random, np.kind))
  } else {
    court.value?.flash(`+${np.n} PUNTOS`, '#7dd3fc')
    await sleep(900)
  }
  const g = cur.lastGame
  if (alive && g && JSON.stringify(g) !== JSON.stringify(prev.lastGame)) {
    const winner = g.lostServe ? 1 - idx(g.lostServe) : idx(g.server)
    if (winner != null) {
      court.value?.flash(`${g.lostServe ? 'BREAK' : 'JUEGO'} ${names.value[winner]}`.toUpperCase().slice(0, 22), g.lostServe ? '#fca5a5' : '#7dd3fc')
      await sleep(800)
    }
  }
}

watch(reading, (cur, prev) => {
  if (!cur || !prev) return
  const np = newPoints(prev, cur)
  if (!np || np.n === 0 || np.n > 12) return
  queue = queue.then(() => animate(np, prev, cur)).catch(() => {})
})
onBeforeUnmount(() => { alive = false })
</script>
