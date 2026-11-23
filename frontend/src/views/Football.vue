<template>
  <!-- Football lives on its own page: La Liga and Premier League only. Nothing here is shared with the tennis views. -->
  <div>
    <div class="mb-2 flex flex-wrap items-baseline justify-between gap-2">
      <h1 class="text-2xl font-bold text-slate-900">Fútbol</h1>
      <span class="text-xs text-slate-500">La Liga y Premier League · mercado principal: Más/Menos 2.5 goles</span>
    </div>
    <p class="mb-4 text-xs text-slate-500">
      Las cuotas se guardan desde el 23-nov: todavía no hay muestra para saber si el modelo le gana a la casa,
      por eso casi todo sale "sin valor" (el modelo no pesa en el edge hasta demostrarlo).
    </p>

    <p v-if="loading" class="text-sm text-slate-500">Cargando…</p>
    <p v-else-if="error" class="text-sm text-amber-800">No se pudo cargar: {{ error }}</p>
    <div v-else-if="!matches.length" class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
      No hay partidos de La Liga ni de la Premier en estos días.
    </div>

    <template v-else>
      <section v-for="g in groups" :key="g.title" class="mb-6">
        <h2 class="mb-2 text-sm font-semibold text-slate-700">{{ g.title }} <span class="font-normal text-slate-500">({{ g.items.length }})</span></h2>
        <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <FootballCard v-for="m in g.items" :key="m.matchId" :match="m" :predictions="byMatch[m.matchId] || []" />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '../stores/api.js'
import FootballCard from '../components/FootballCard.vue'

const matches = ref([])
const preds = ref([])
const loading = ref(true)
const error = ref('')

const day = (offset) => new Date(Date.now() + offset * 86400000).toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })

onMounted(async () => {
  try {
    const from = day(-1)
    const to = day(2)
    const [m, p] = await Promise.all([
      api.get('/matches/by-date', { params: { from, to } }),
      api.get('/predictions/history', { params: { sport: 'football', from, to, limit: 200 } })
    ])
    matches.value = (m.data.football || []).slice().sort((a, b) => `${a.eventDate} ${a.eventTime}`.localeCompare(`${b.eventDate} ${b.eventTime}`))
    preds.value = p.data.predictions || []
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})

const byMatch = computed(() => {
  const out = {}
  for (const p of preds.value) (out[p.matchId] ||= []).push(p)
  return out
})

const groups = computed(() => {
  const open = matches.value.filter((m) => m.status !== 'FINISHED' && m.status !== 'CANCELLED')
  const done = matches.value.filter((m) => m.status === 'FINISHED').reverse()
  return [
    { title: 'Por jugar', items: open },
    { title: 'Terminados', items: done }
  ].filter((g) => g.items.length)
})
</script>
