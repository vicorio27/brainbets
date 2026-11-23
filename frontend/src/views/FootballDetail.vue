<template>
  <div>
    <router-link to="/futbol" class="text-xs text-blue-700 hover:underline">← Volver a Fútbol</router-link>
    <p v-if="loading" class="mt-3 text-sm text-slate-500">Cargando…</p>
    <p v-else-if="!match" class="mt-3 text-sm text-amber-800">No se encontró el partido.</p>
    <template v-else>
      <div class="mt-2 text-xs text-slate-500">{{ match.league }} · {{ match.eventDate }} {{ match.eventTime }}</div>
      <h1 class="text-xl font-bold text-slate-900">
        {{ match.homeTeam }}
        <span v-if="match.homeScore != null" class="tabular-nums">{{ match.homeScore }} - {{ match.awayScore }}</span><span v-else class="text-slate-400"> vs </span>
        {{ match.awayTeam }}
      </h1>

      <section class="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
        <h2 class="text-sm font-semibold text-emerald-900">Lo más probable</h2>
        <p v-if="!picks.length" class="mt-1 text-xs text-slate-600">Todavía no hay datos para este partido.</p>
        <ul v-else class="mt-2 space-y-1">
          <li v-for="p in picks" :key="p.key" class="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span class="text-slate-900">{{ p.text }}</span>
            <span class="text-xs text-slate-700">
              <b class="tabular-nums">{{ Math.round(p.prob * 100) }}%</b>
              <span v-if="p.odds"> · cuota {{ p.odds.toFixed(2) }}</span>
              <span class="ml-1 rounded px-1.5 py-0.5" :class="p.source === 'casa' ? 'bg-white text-emerald-800' : 'bg-amber-100 text-amber-900'">{{ p.source === 'casa' ? 'según la casa' : 'según el modelo' }}</span>
            </span>
          </li>
        </ul>
        <p class="mt-2 text-xs text-slate-600">
          Lo que más probablemente pasa, no lo que más paga: las más seguras pagan poco. Con la casa = su probabilidad sin margen;
          con el modelo = Poisson, que todavía no se ha medido contra la cuota. En la base, Más de 0.5 sale 93% y Más de 1.5 75%.
        </p>
      </section>

      <section v-if="predictions.length" class="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <h2 class="text-sm font-semibold text-slate-800">Predicciones del modelo</h2>
        <div v-for="p in predictions" :key="p.predictionId" class="mt-1 flex justify-between text-xs">
          <span><span class="text-slate-500">{{ p.market }}:</span> <b>{{ p.prediction }}</b></span>
          <span class="text-slate-600">modelo {{ p.confidence }}%</span>
        </div>
      </section>

      <section v-if="match.goalsTrend" class="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700">
        <h2 class="mb-1 text-sm font-semibold text-slate-800">Goles de cada equipo</h2>
        <template v-for="[team, x] in [[match.homeTeam, match.goalsTrend.home], [match.awayTeam, match.goalsTrend.away]]" :key="team">
          <div v-if="x"><b>{{ team }}:</b> {{ x.goalsFor }} a favor y {{ x.goalsAgainst }} en contra por partido; más de 2.5 en {{ Math.round(x.over25 * 100) }}% (últimos {{ x.n }})</div>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../stores/api.js'
import { likelyPicks } from '../utils/footballPicks.js'

const route = useRoute()
const match = ref(null)
const predictions = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const d = route.query.date
    const r = await api.get('/matches/by-date', { params: { from: d, to: d } })
    match.value = (r.data.football || []).find((m) => m.matchId === route.params.id) || null
    const p = await api.get('/predictions/history', { params: { sport: 'football', matchId: route.params.id, limit: 20 } })
    predictions.value = p.data.predictions || []
  } catch (e) { match.value = null } finally { loading.value = false }
})

const picks = computed(() => (match.value ? likelyPicks(match.value) : []))
</script>
