<template>
  <!-- Football lives on its own page: La Liga and Premier League only. Nothing here is shared with the tennis views. -->
  <div>
    <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <h1 class="text-2xl font-bold text-slate-900">Fútbol</h1>
      <span class="text-xs text-slate-500">La Liga, Premier League y Champions League · mercado principal: Más/Menos 2.5 goles</span>
    </div>
    <p class="mb-4 text-xs text-slate-500">
      Las cuotas se guardan desde el 23-nov: todavía no hay muestra para saber si el modelo le gana a la casa,
      por eso casi todo sale "sin valor" (el modelo no pesa en el edge hasta demostrarlo).
    </p>

    <section v-if="pod" class="mb-4 rounded-lg border-l-4 border-emerald-600 bg-white p-3 shadow-sm">
      <div class="text-xs font-semibold uppercase tracking-wide text-emerald-800">
        Apuesta del día · la más probable con cuota de la casa
      </div>
      <div class="mt-1 text-base font-bold text-slate-900">{{ pod.pick.text }}</div>
      <div class="text-sm text-slate-700">
        {{ pod.match.homeTeam }} vs {{ pod.match.awayTeam }} · {{ pod.match.league }} · {{ pod.match.eventDate }} {{ pod.match.eventTime }}
      </div>
      <div class="mt-1 text-sm text-slate-800">
        Probabilidad <b>{{ Math.round(pod.pick.prob * 100) }}%</b> (casa, sin margen) · cuota <b>{{ pod.pick.odds.toFixed(2) }}</b>
        · paga {{ Math.round((pod.pick.odds - 1) * 100) }} por cada 100
      </div>
      <router-link :to="{ path: `/futbol/${pod.match.matchId}`, query: { date: pod.match.eventDate } }" class="mt-1 inline-block text-xs font-medium text-blue-700 hover:underline">Ver el partido →</router-link>
      <p class="mt-1 text-xs text-slate-500">
        Es lo que más probablemente pasa, no lo que más paga, y todavía no hay muestra que diga si le gana a la cuota.
        Se calcula con los mercados de la casa (goles, doble oportunidad, córners, mitades); sin cuota no entra.
      </p>
    </section>

    <details v-if="lab"class="mb-4 rounded-lg border border-slate-200 bg-white">
      <summary class="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
        <span class="font-medium text-slate-800">Laboratorio · Más/Menos 2.5 goles</span>
        <span class="text-xs text-slate-600">{{ verdictText(lab) }}</span>
      </summary>
      <div class="space-y-1 border-t border-slate-100 px-3 py-2 text-xs text-slate-700">
        <p>
          Pregunta: ¿el modelo de Poisson aporta algo que la cuota no tenga? La base es la probabilidad de la casa sin margen y
          el modelo solo puede moverla, con un parámetro ajustado con días anteriores. Se mira cuando haya {{ lab.verdict.needed }}
          partidos nuevos y el intervalo de la mejora no incluya el cero.
        </p>
        <p>Partidos con cuota previa y predicción: <b>{{ lab.rows }}</b></p>
        <p v-if="lab.marketCheck && lab.marketCheck.matches">
          En esos partidos la casa daba Más 2.5 al {{ pct(lab.marketCheck.marketOver) }}%, el modelo al {{ pct(lab.marketCheck.modelOver) }}%
          y salió el {{ pct(lab.marketCheck.actualOver) }}%.
        </p>
        <p v-if="lab.postFreeze && lab.postFreeze.matches">
          Probado hacia adelante en {{ lab.postFreeze.matches }} partidos: mejora del log-loss {{ lab.postFreeze.improvement }}
          (intervalo {{ lab.postFreeze.improvementCiLow }} a {{ lab.postFreeze.improvementCiHigh }}).
          <span v-if="lab.postFreeze.bets">Apostando donde el modelo discrepa 3 puntos o más: {{ lab.postFreeze.bets }} apuestas, rendimiento {{ lab.postFreeze.yield }}%.</span>
        </p>
        <p class="text-slate-500">No hay histórico de cuotas anterior al 23-nov, así que la muestra solo crece con los días. Reporta, no cambia ninguna predicción.</p>
      </div>
    </details>

    <details v-if="corners" class="mb-4 rounded-lg border border-slate-200 bg-white">
      <summary class="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
        <span class="font-medium text-slate-800">Laboratorio · Córners totales</span>
        <span class="text-xs text-slate-600">{{ verdictText(corners) }}</span>
      </summary>
      <div class="space-y-1 border-t border-slate-100 px-3 py-2 text-xs text-slate-700">
        <p>
          Pregunta: ¿un modelo de córners aporta algo que la cuota no tenga? La base es la probabilidad de la casa sin margen en la
          línea de córners más equilibrada; el modelo (equipos a favor y en contra frente al promedio de la liga, solo con partidos
          anteriores) solo puede moverla. Congelado el {{ corners.frozenAt }}. Se mira cuando haya {{ corners.verdict.needed }}
          partidos nuevos y el intervalo de la mejora no incluya el cero.
        </p>
        <p>Partidos con cuota de córners y estadísticas: <b>{{ corners.rows }}</b></p>
        <p v-if="corners.marketCheck && corners.marketCheck.matches">
          En esos partidos la casa daba Más al {{ pct(corners.marketCheck.marketOver) }}%, el modelo al {{ pct(corners.marketCheck.modelOver) }}%
          y salió el {{ pct(corners.marketCheck.actualOver) }}%.
        </p>
        <p v-if="corners.postFreeze && corners.postFreeze.matches">
          Probado hacia adelante en {{ corners.postFreeze.matches }} partidos: mejora del log-loss {{ corners.postFreeze.improvement }}
          (intervalo {{ corners.postFreeze.improvementCiLow }} a {{ corners.postFreeze.improvementCiHigh }}).
        </p>
        <p class="text-slate-500">Las cuotas de córners existen desde el 24-nov, así que la muestra solo crece con los días. Reporta, no cambia ninguna predicción.</p>
      </div>
    </details>

    <p v-if="loading" class="text-sm text-slate-500">Cargando…</p>
    <p v-else-if="error" class="text-sm text-amber-800">No se pudo cargar: {{ error }}</p>
    <div v-else-if="!matches.length" class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
      No hay partidos de La Liga ni de la Premier en estos días.
    </div>

    <template v-else>
      <section v-for="lg in leagues" :key="lg.name" class="mb-8">
        <h2 class="mb-2 border-b border-slate-200 pb-1 text-base font-bold text-slate-900">{{ lg.name }}</h2>
        <div v-for="g in lg.groups" :key="g.title" class="mb-4">
          <h3 class="mb-2 text-sm font-semibold text-slate-700">{{ g.title }} <span class="font-normal text-slate-500">({{ g.items.length }})</span></h3>
          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <FootballCard v-for="m in g.items" :key="m.matchId" :match="m" :predictions="byMatch[m.matchId] || []" />
          </div>
        </div>
      </section>
    </template>
    <ComboBar sport="football" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../stores/api.js'
import FootballCard from '../components/FootballCard.vue'
import ComboBar from '../components/ComboBar.vue'
import { pickOfDay } from '../utils/footballPicks.js'

const matches = ref([])
const preds = ref([])
const lab = ref(null)
const corners = ref(null)
const loading = ref(true)
const error = ref('')

const day = (offset) => new Date(Date.now() + offset * 86400000).toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })

onMounted(async () => {
  try {
    const from = day(-1)
    const to = day(3)
    const [m, p] = await Promise.all([
      api.get('/matches/by-date', { params: { from, to } }),
      api.get('/predictions/history', { params: { sport: 'football', from, to, limit: 200 } })
    ])
    matches.value = (m.data.football || []).slice().sort((a, b) => `${a.eventDate} ${a.eventTime}`.localeCompare(`${b.eventDate} ${b.eventTime}`))
    preds.value = p.data.predictions || []
    try { lab.value = (await api.get('/analytics/football-lab')).data } catch (e) { lab.value = null }
    try { corners.value = (await api.get('/analytics/football-corners-lab')).data } catch (e) { corners.value = null }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})

const pct = (x) => Math.round((x ?? 0) * 100)
const verdictText = (report) => {
  const v = report?.verdict
  if (!v) return ''
  const words = { juntando_muestra: `juntando muestra: ${v.matches} de ${v.needed}`, no_demostrado: 'no demostrado', demostrado: 'demostrado', descartado: 'descartado' }
  return words[v.level] || v.level
}

const nowBogota = () => new Date().toLocaleString('sv-SE', { timeZone: 'America/Bogota' }).slice(0, 16)
const pod = computed(() => pickOfDay(matches.value, nowBogota()))

const byMatch = computed(() => {
  const out = {}
  for (const p of preds.value) (out[p.matchId] ||= []).push(p)
  return out
})

// One section per league (La Liga / Premier League), each with its own "por jugar" and "terminados".
const groupsOf = (list) => {
  const open = list.filter((m) => m.status !== 'FINISHED' && m.status !== 'CANCELLED')
  const done = list.filter((m) => m.status === 'FINISHED').reverse()
  return [
    { title: 'Por jugar', items: open },
    { title: 'Terminados', items: done }
  ].filter((g) => g.items.length)
}
const leagues = computed(() => {
  const names = [...new Set(matches.value.map((m) => m.league))].sort()
  return names.map((name) => ({ name, groups: groupsOf(matches.value.filter((m) => m.league === name)) }))
})
</script>
