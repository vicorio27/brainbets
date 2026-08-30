<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Partidos</h1>

    <!-- Filters -->
    <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
      <div class="flex flex-col sm:flex-row sm:items-center gap-4 flex-wrap">
        <label class="text-sm font-medium text-slate-700">Desde:</label>
        <input
          v-model="dateFrom"
          type="date"
          aria-label="Fecha desde"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <label class="text-sm font-medium text-slate-700">Hasta:</label>
        <input
          v-model="dateTo"
          type="date"
          aria-label="Fecha hasta"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <label class="text-sm font-medium text-slate-700">Deporte:</label>
        <select
          v-model="sport"
          aria-label="Filtrar por deporte"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="all">Todos</option>
          <option value="football">⚽ Fútbol</option>
          <option value="tennis">🎾 Tenis</option>
        </select>
        <label class="text-sm font-medium text-slate-700">Por página:</label>
        <select
          v-model.number="pageSize"
          aria-label="Resultados por página"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <label class="text-sm font-medium text-slate-700">Orden:</label>
        <select
          v-model="sort"
          aria-label="Orden cronológico"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="desc">Más recientes primero</option>
          <option value="asc">Más antiguos primero</option>
        </select>
        <button @click="reset" class="px-3 py-2 text-sm text-blue-600 hover:text-blue-800 font-medium">
          Limpiar
        </button>
      </div>
    </div>

    <div v-if="matchesStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      <p class="mt-4 text-slate-600">Cargando datos...</p>
    </div>

    <div v-else-if="matchesStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ matchesStore.error }}
    </div>

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div>
        <h2 class="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <span>🎾</span> Tenis
          <span class="text-sm font-normal text-slate-500">({{ tennisMatches.length }})</span>
        </h2>
        <div class="space-y-4">
          <MatchCard
            v-for="match in tennisMatches"
            :key="match.matchId"
            :match="match"
            sport="tennis"
            :best-confidence="bestConfidenceByMatch[match.matchId] ?? null"
          />
          <EmptyState
            v-if="!tennisMatches.length"
            icon="🎾"
            title="No hay partidos de tenis"
            message="No se encontraron partidos en el rango seleccionado."
          />
        </div>
      </div>

      <div>
        <h2 class="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <span>⚽</span> Fútbol
          <span class="text-sm font-normal text-slate-500">({{ footballMatches.length }})</span>
        </h2>
        <div class="space-y-4">
          <MatchCard
            v-for="match in footballMatches"
            :key="match.matchId"
            :match="match"
            sport="football"
            :best-confidence="bestConfidenceByMatch[match.matchId] ?? null"
          />
          <EmptyState
            v-if="!footballMatches.length"
            icon="⚽"
            title="No hay partidos de fútbol"
            message="No se encontraron partidos en el rango seleccionado."
          />
        </div>
      </div>
    </div>

    <div v-if="totalItems > pageSize" class="mt-8">
      <Pagination v-model:current-page="currentPage" :total-items="totalItems" :page-size="pageSize" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useMatchesStore } from '../stores/matches.js'
import { usePredictionsStore } from '../stores/predictions.js'
import MatchCard from '../components/MatchCard.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'

const matchesStore = useMatchesStore()
const predictionsStore = usePredictionsStore()

function todayStr() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
}

const dateFrom = ref('')
const dateTo = ref('')
const sport = ref('all')
const sort = ref('desc')
const pageSize = ref(20)
const currentPage = ref(1)

const bestConfidenceByMatch = computed(() => {
  const map = {}
  for (const pred of predictionsStore.latest?.predictions || []) {
    const conf = pred.calibratedConfidence ?? pred.confidence
    if (conf == null) continue
    if (map[pred.matchId] == null || conf > map[pred.matchId]) map[pred.matchId] = conf
  }
  return map
})

function sortByConfidence(matches) {
  const map = bestConfidenceByMatch.value
  return [...matches].sort((a, b) => {
    const ca = map[a.matchId]
    const cb = map[b.matchId]
    if (ca == null && cb == null) return 0
    if (ca == null) return 1
    if (cb == null) return -1
    return cb - ca
  })
}

const tennisMatches = computed(() => sortByConfidence(matchesStore.latest?.tennis || []))
const footballMatches = computed(() => sortByConfidence(matchesStore.latest?.football || []))
const totalItems = computed(() => matchesStore.latest?.total || 0)

function load() {
  const from = dateFrom.value || '2010-01-01'
  const to = dateTo.value || todayStr()
  matchesStore.fetchHistory(from, to, sport.value, currentPage.value, pageSize.value, sort.value)
  predictionsStore.fetchLatest()
}

function reset() {
  dateFrom.value = ''
  dateTo.value = ''
  sport.value = 'all'
  sort.value = 'desc'
  currentPage.value = 1
}

watch([dateFrom, dateTo, sport, sort, pageSize], () => {
  currentPage.value = 1
  load()
})
watch(currentPage, load)

onMounted(load)
</script>
