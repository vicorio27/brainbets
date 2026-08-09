<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Predicciones</h1>

    <!-- Match Filter Banner -->
    <div v-if="matchId" class="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <p class="text-sm text-blue-700 font-medium">Filtrando por partido</p>
          <p class="text-lg font-semibold text-slate-900">{{ matchDisplayName }}</p>
          <p class="text-sm text-slate-500">{{ matchDate }}</p>
        </div>
        <router-link
          to="/predictions"
          class="px-4 py-2 bg-white border border-blue-300 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-100 transition-colors text-center"
        >
          Ver todas las predicciones
        </router-link>
      </div>
    </div>

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

    <div v-if="predictionsStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      <p class="mt-4 text-slate-600">Cargando predicciones...</p>
    </div>

    <div v-else-if="predictionsStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ predictionsStore.error }}
    </div>

    <div v-else>
      <!-- History Filters -->
      <div v-if="activeTab === 'history' && !matchId" class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
        <div class="flex flex-col sm:flex-row sm:items-center gap-4 flex-wrap">
          <label class="text-sm font-medium text-slate-700">Nombre:</label>
          <input
            v-model="historyName"
            type="text"
            placeholder="Jugador o equipo..."
            class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
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
          <label class="text-sm font-medium text-slate-700">Estado:</label>
          <select
            v-model="historyStatus"
            class="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="all">Todos</option>
            <option value="PENDING">⏳ Pendiente</option>
            <option value="VALIDATED">✅ Acertada</option>
            <option value="FAILED">❌ Fallida</option>
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
          <button
            @click="resetHistoryFilters"
            class="px-3 py-2 text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            Limpiar
          </button>
        </div>
      </div>

      <p class="text-sm text-slate-500 mb-4">
        Mostrando {{ predictions.length }} de {{ totalItems }} predicciones
      </p>

      <PredictionTable
        :predictions="predictions"
        :generated-at="predictionsStore.latest?.generatedAt"
        :matches="matchesStore.latest"
      />

      <Pagination
        v-if="totalItems > pageSize"
        v-model:current-page="currentPage"
        :total-items="totalItems"
        :page-size="pageSize"
        class="mt-4"
      />

      <EmptyState
        v-if="!predictions.length"
        icon="🎯"
        title="No hay predicciones"
        :message="emptyMessage"
        class="mt-6"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePredictionsStore } from '../stores/predictions.js'
import { useMatchesStore } from '../stores/matches.js'
import PredictionTable from '../components/PredictionTable.vue'
import EmptyState from '../components/EmptyState.vue'
import Pagination from '../components/Pagination.vue'
import { formatDateTime } from '../utils/format.js'

const route = useRoute()
const router = useRouter()
const predictionsStore = usePredictionsStore()
const matchesStore = useMatchesStore()

const activeTab = ref('today')
const currentPage = ref(1)
const pageSize = ref(20)

const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
const historyDateFrom = ref('')
const historyDateTo = ref('')
const historySport = ref('all')
const historyStatus = ref('all')
const historyName = ref('')

const matchId = computed(() => route.query.matchId || null)
const matchDate = computed(() => route.query.date || null)

const isMatchToday = computed(() => matchDate.value === todayStr)

const matchDisplayName = computed(() => {
  if (!matchId.value || !matchesStore.latest) return matchId.value
  const tennisMatch = matchesStore.latest.tennis?.find(m => m.matchId === matchId.value)
  if (tennisMatch) return `${tennisMatch.player1} vs ${tennisMatch.player2}`
  const footballMatch = matchesStore.latest.football?.find(m => m.matchId === matchId.value)
  if (footballMatch) return `${footballMatch.homeTeam} vs ${footballMatch.awayTeam}`
  return matchId.value
})

const todayPredictions = computed(() => {
  const preds = predictionsStore.latest?.predictions || []
  let filtered = preds.filter(pred => pred.eventDate === todayStr)
  if (matchId.value) {
    filtered = filtered.filter(pred => pred.matchId === matchId.value)
  }
  return filtered
})

const historyPredictions = computed(() => {
  // El filtro por matchId ya se aplica server-side en fetchHistory.
  let preds = predictionsStore.history?.predictions || []
  if (historyStatus.value && historyStatus.value !== 'all') {
    preds = preds.filter(pred => pred.status === historyStatus.value)
  }
  return preds
})

const predictions = computed(() => {
  if (matchId.value) {
    return activeTab.value === 'today' ? todayPredictions.value : historyPredictions.value
  }
  return activeTab.value === 'today' ? todayPredictions.value : historyPredictions.value
})

const totalItems = computed(() => {
  if (activeTab.value === 'today') {
    return predictions.value.length
  }
  return predictionsStore.history?.total || 0
})

const statusLabels = {
  PENDING: 'pendientes',
  VALIDATED: 'acertadas',
  FAILED: 'fallidas'
}

const emptyMessage = computed(() => {
  if (matchId.value) {
    return 'No hay predicciones para este partido.'
  }
  if (activeTab.value === 'today') {
    return 'No hay predicciones para partidos de hoy.'
  }
  const parts = []
  if (historySport.value && historySport.value !== 'all') {
    parts.push(historySport.value === 'football' ? 'fútbol' : 'tenis')
  }
  if (historyStatus.value && historyStatus.value !== 'all') {
    parts.push(statusLabels[historyStatus.value] || historyStatus.value)
  }
  if (parts.length) {
    return `No se encontraron predicciones para ${parts.join(' / ')}.`
  }
  return 'No hay predicciones en el historial.'
})

function resetHistoryFilters() {
  historyDateFrom.value = ''
  historyDateTo.value = ''
  historySport.value = 'all'
  historyStatus.value = 'all'
  historyName.value = ''
  currentPage.value = 1
}

function loadToday() {
  predictionsStore.fetchLatest()
  if (matchId.value) {
    matchesStore.fetchByDate(matchDate.value || todayStr)
  } else {
    matchesStore.fetchByDate(todayStr)
  }
}

function loadHistory() {
  const from = historyDateFrom.value || '2010-01-01'
  const to = historyDateTo.value || todayStr
  const status = historyStatus.value !== 'all' ? historyStatus.value : null
  predictionsStore.fetchHistory(historySport.value, from, to, status, currentPage.value, pageSize.value, matchId.value, historyName.value)
  matchesStore.fetchHistory(from, to, historySport.value, currentPage.value, pageSize.value)
}

function initializeFromRoute() {
  if (matchId.value) {
    activeTab.value = isMatchToday.value ? 'today' : 'history'
  }
  currentPage.value = 1
}

watch(() => route.query.matchId, () => {
  initializeFromRoute()
  if (activeTab.value === 'today') {
    loadToday()
  } else {
    loadHistory()
  }
})

watch(activeTab, (tab) => {
  currentPage.value = 1
  if (tab === 'today') {
    loadToday()
  } else {
    loadHistory()
  }
})

watch([historyDateFrom, historyDateTo, historySport], () => {
  currentPage.value = 1
  if (activeTab.value === 'history') {
    loadHistory()
  }
})

let nameDebounce = null
watch(historyName, () => {
  clearTimeout(nameDebounce)
  nameDebounce = setTimeout(() => {
    currentPage.value = 1
    if (activeTab.value === 'history') {
      loadHistory()
    }
  }, 400)
})

watch(currentPage, () => {
  if (activeTab.value === 'history') {
    loadHistory()
  }
})

watch(historyStatus, () => {
  currentPage.value = 1
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
  initializeFromRoute()
  if (activeTab.value === 'today') {
    loadToday()
  } else {
    loadHistory()
  }
})
</script>
