<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Dashboard</h1>

    <!-- Tabs -->
    <div class="border-b border-slate-200 mb-6">
      <nav class="-mb-px flex gap-6" aria-label="Tabs">
        <button
          @click="activeTab = 'today'"
          :class="activeTab === 'today'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'"
          class="whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm"
        >
          Hoy
        </button>
        <button
          @click="activeTab = 'history'"
          :class="activeTab === 'history'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'"
          class="whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm"
        >
          Histórico
        </button>
      </nav>
    </div>

    <!-- History Filters -->
    <div v-if="activeTab === 'history'" class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
      <div class="flex flex-col sm:flex-row sm:items-center gap-4 flex-wrap">
        <label class="text-sm font-medium text-slate-700">Desde:</label>
        <input
          v-model="historyDateFrom"
          type="date"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <label class="text-sm font-medium text-slate-700">Hasta:</label>
        <input
          v-model="historyDateTo"
          type="date"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <label class="text-sm font-medium text-slate-700">Deporte:</label>
        <select
          v-model="historySport"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="all">Todos</option>
          <option value="football">⚽ Fútbol</option>
          <option value="tennis">🎾 Tenis</option>
        </select>
        <label class="text-sm font-medium text-slate-700">Por página:</label>
        <select
          v-model.number="pageSize"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <label class="text-sm font-medium text-slate-700">Orden:</label>
        <select
          v-model="historySort"
          class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="desc">Más recientes primero</option>
          <option value="asc">Más antiguos primero</option>
        </select>
        <button
          @click="resetHistoryFilters"
          class="px-3 py-2 text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
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
      <!-- Tennis Matches -->
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
            :is-top="top3MatchIds.has(match.matchId)"
          />
          <EmptyState
            v-if="!tennisMatches.length"
            icon="🎾"
            title="No hay partidos de tenis"
            :message="emptyMessage"
          />
        </div>
      </div>

      <!-- Football Matches -->
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
            :is-top="top3MatchIds.has(match.matchId)"
          />
          <EmptyState
            v-if="!footballMatches.length"
            icon="⚽"
            title="No hay partidos de fútbol"
            :message="emptyMessage"
          />
        </div>
      </div>
    </div>

    <!-- Player set stats (tennis, today) -->
    <div v-if="activeTab === 'today' && setStatsPlayers.length" class="mt-8 bg-white rounded-lg shadow-sm border border-slate-200 p-4">
      <h2 class="text-lg font-semibold text-slate-900 mb-1">🎾 Games y puntos por set — jugadores de hoy</h2>
      <p class="text-sm text-slate-500 mb-4">
        Promedio de games y puntos ganados-perdidos por set en cada superficie, sobre los partidos con detalle por set.
      </p>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
              <th class="py-2 pr-4">Jugador</th>
              <th class="py-2 px-3">🟠 Arcilla</th>
              <th class="py-2 px-3">🔵 Dura</th>
              <th class="py-2 px-3">🟢 Hierba</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in setStatsPlayers" :key="p.matchId + p.name" class="border-t border-slate-100">
              <td class="py-2 pr-4 font-medium text-slate-900 whitespace-nowrap">{{ p.name }}</td>
              <td v-for="surf in ['clay', 'hard', 'grass']" :key="surf" class="py-2 px-3 whitespace-nowrap">
                <span
                  v-if="p.surfaces[surf]"
                  class="inline-block px-2 py-0.5 rounded"
                  :class="surf === p.matchSurface ? 'bg-blue-100/70 ring-1 ring-blue-300' : ''"
                >
                  {{ p.surfaces[surf].avgGamesWon }}-{{ p.surfaces[surf].avgGamesLost }}
                  <span class="text-xs text-slate-400">({{ p.surfaces[surf].setsPlayed }})</span>
                  <div v-if="p.surfaces[surf].avgPointsWon != null" class="text-xs text-slate-500">
                    {{ p.surfaces[surf].avgPointsWon }}-{{ p.surfaces[surf].avgPointsLost }} pts
                  </div>
                </span>
                <span v-else class="text-xs text-slate-300">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-slate-400 mt-2">
        Formato: games ganados-perdidos por set (sets con datos) y, debajo, puntos por set cuando hay estadísticas.
        Resaltado = superficie del partido de hoy.
      </p>
    </div>

    <!-- Pagination -->
    <div v-if="activeTab === 'history' && totalItems > pageSize" class="mt-8">
      <Pagination
        v-model:current-page="currentPage"
        :total-items="totalItems"
        :page-size="pageSize"
      />
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

const activeTab = ref('today')
const pageSize = ref(20)
const currentPage = ref(1)

function getUtcTodayStr() {
  // Use America/Bogota timezone (UTC-5) so "today" matches the user's local date
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
}

const historyDateFrom = ref('')
const historyDateTo = ref('')
const historySport = ref('all')
const historySort = ref('desc')

// Best (max) confidence per match, using calibrated confidence when available
const bestConfidenceByMatch = computed(() => {
  const map = {}
  for (const pred of predictionsStore.latest?.predictions || []) {
    const conf = pred.calibratedConfidence ?? pred.confidence
    if (conf == null) continue
    if (map[pred.matchId] == null || conf > map[pred.matchId]) {
      map[pred.matchId] = conf
    }
  }
  return map
})

// Matches with predictions first (highest confidence -> lowest), then the rest in original order
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

// Top 3 matches by confidence (across both sports) get the fire badge
const top3MatchIds = computed(() => {
  const map = bestConfidenceByMatch.value
  const ids = Object.keys(map).sort((a, b) => map[b] - map[a])
  return new Set(ids.slice(0, 3))
})

const tennisMatches = computed(() => sortByConfidence(matchesStore.latest?.tennis || []))
const footballMatches = computed(() => sortByConfidence(matchesStore.latest?.football || []))
const totalItems = computed(() => matchesStore.latest?.total || 0)
const setStatsPlayers = computed(() => matchesStore.playerSetStats?.players || [])

const emptyMessage = computed(() => {
  if (activeTab.value === 'history') {
    return 'No se encontraron partidos en el rango seleccionado.'
  }
  return 'No hay partidos disponibles para hoy.'
})

function resetHistoryFilters() {
  historyDateFrom.value = ''
  historyDateTo.value = ''
  historySport.value = 'all'
  historySort.value = 'desc'
  currentPage.value = 1
}

function loadToday() {
  matchesStore.fetchByDate(getUtcTodayStr())
  matchesStore.fetchPlayerSetStats(getUtcTodayStr())
  predictionsStore.fetchLatest()
}

function loadHistory() {
  const from = historyDateFrom.value || '2010-01-01'
  const to = historyDateTo.value || getUtcTodayStr()
  matchesStore.fetchHistory(from, to, historySport.value, currentPage.value, pageSize.value, historySort.value)
  predictionsStore.fetchLatest()
}

watch(activeTab, (tab) => {
  currentPage.value = 1
  if (tab === 'today') {
    loadToday()
  } else {
    loadHistory()
  }
})

watch([historyDateFrom, historyDateTo, historySport, historySort], () => {
  currentPage.value = 1
  if (activeTab.value === 'history') {
    loadHistory()
  }
})

watch(currentPage, () => {
  if (activeTab.value === 'history') {
    loadHistory()
  }
})

watch(pageSize, () => {
  currentPage.value = 1
  if (activeTab.value === 'history') {
    loadHistory()
  }
})

onMounted(() => {
  loadToday()
})
</script>
