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

      <!-- Point model for this match (still to play) -->
      <div v-if="pointBox" class="mt-3 rounded border border-slate-200 bg-white p-3 text-sm text-slate-700"
        title="Modelo de puntos (saque y resto, punto a punto) con la corrección de games congelada el 16-oct-2026. Segunda opinión: no ha demostrado ganarle a la casa.">
        <p class="font-semibold text-slate-900 mb-1">
          Modelo de puntos
          <span v-if="pointBox.close" class="ml-1 text-sky-800">· ⚖ Partido reñido</span>
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
          <div>Ganador: {{ pointBox.p1 }} <strong>{{ pointBox.match1 }}%</strong> · {{ pointBox.p2 }} <strong>{{ pointBox.match2 }}%</strong></div>
          <div>1er set: {{ pointBox.p1 }} <strong>{{ pointBox.set1 }}%</strong> · {{ pointBox.p2 }} <strong>{{ pointBox.set2 }}%</strong></div>
          <div>~<strong>{{ pointBox.g.expectedGames }}</strong> games · tiebreak <strong>{{ pointBox.tiebreak }}%</strong> · {{ pointBox.deciderLabel }} <strong>{{ pointBox.decider }}%</strong></div>
          <div v-if="pointBox.g.line">
            Línea {{ pointBox.g.line.line }} games: Más modelo <strong>{{ pct(pointBox.g.line.modelOver) }}%</strong> · casa {{ pct(pointBox.g.line.marketOver) }}%
          </div>
          <div class="sm:col-span-2 flex flex-wrap gap-x-2">
            <span>Marcador:</span>
            <span v-for="sc in pointBox.scores" :key="sc.key" class="whitespace-nowrap">{{ sc.label }} <strong>{{ sc.pct }}%</strong></span>
          </div>
        </div>
        <p v-if="pointBox.g.trust < 0.5" class="text-xs text-slate-500 mt-1">Poca historia de saque y resto de alguno de los dos.</p>
      </div>

      <!-- Head-to-head: every stored meeting between the two players -->
      <div v-if="h2hBox" class="mt-3 rounded border border-slate-200 bg-white p-3 text-sm text-slate-700">
        <p class="font-semibold text-slate-900 mb-1">
          H2H: {{ h2hBox.p1 }} {{ h2hBox.h ? h2hBox.h.p1Wins : 0 }}-{{ h2hBox.h ? h2hBox.h.p2Wins : 0 }} {{ h2hBox.p2 }}
        </p>
        <p v-if="!h2hBox.h" class="text-slate-500">Nunca se han enfrentado en los partidos ATP guardados (desde 2010).</p>
        <ul v-else class="space-y-0.5">
          <li v-for="mt in h2hBox.h.meetings" :key="mt.date" class="flex flex-wrap gap-x-2">
            <span class="text-slate-500">{{ mt.date }}</span>
            <span>{{ mt.tournament || '?' }}<template v-if="mt.surface"> ({{ surfaceEs[mt.surface] || mt.surface }})</template></span>
            <span>ganó <strong>{{ mt.winner === 'p1' ? h2hBox.p1 : h2hBox.p2 }}</strong><template v-if="mt.sets">&nbsp;{{ mt.sets }}</template></span>
            <span v-if="mt.games" class="text-slate-500">{{ mt.games.join(' ') }}</span>
          </li>
          <li v-if="h2hBox.h.total > h2hBox.h.meetings.length" class="text-slate-500">… y {{ h2hBox.h.total - h2hBox.h.meetings.length }} más</li>
        </ul>
      </div>

      <!-- Player news: off-court factors read from this week's headlines -->
      <div v-if="newsBox" class="mt-3 rounded border border-slate-200 bg-white p-3 text-sm text-slate-700">
        <p class="font-semibold text-slate-900">Noticias de los jugadores</p>
        <p class="text-xs text-slate-500 mb-2">
          Titulares de los últimos 5 días, filtrados por IA: solo lo que podría influir fuera de la cancha. Revisado {{ newsBox.ago }}.
          Es información, no una señal probada: casi todo lo que sale en la prensa ya está en la cuota.
        </p>
        <p v-if="newsBox.n.summary" class="mb-2">{{ newsBox.n.summary }}</p>
        <div v-for="side in newsBox.sides" :key="side.key" class="mb-2 last:mb-0">
          <p class="font-medium text-slate-800">{{ side.name }}</p>
          <p v-if="!side.items.length" class="text-slate-500">Nada relevante (leídos {{ side.read }} titulares).</p>
          <ul v-else class="space-y-1">
            <li v-for="it in side.items" :key="it.link">
              <span class="inline-flex items-center px-1.5 rounded text-xs font-medium mr-1" :class="impactClass[it.impact]">{{ factorEs[it.factor] || it.factor }}</span>
              {{ it.note }}
              <a :href="it.link" target="_blank" rel="noopener noreferrer" class="text-blue-700 underline break-words">{{ it.source }} · {{ it.date }}</a>
            </li>
          </ul>
        </div>
      </div>
      <p v-else-if="h2hBox && newsPending" class="mt-3 text-xs text-slate-500">Noticias de los jugadores: se revisan cada hora para los partidos que empiezan en las próximas 18 horas.</p>
      <!-- The case for the underdog: data-backed arguments, each with what it has been worth -->
      <div v-if="dogBox" class="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-slate-700">
        <p class="font-semibold text-slate-900">¿Le apuesto al no favorito?</p>
        <table class="mt-1 mb-2 text-xs w-full max-w-md">
          <thead><tr class="text-slate-500 text-left"><th class="font-normal">{{ dogBox.underdog }} podría…</th><th class="font-normal">Paga</th><th class="font-normal">Casa</th><th class="font-normal">Modelo de puntos</th></tr></thead>
          <tbody>
            <tr v-for="o in dogBox.options" :key="o.market">
              <td>{{ o.label }}</td>
              <td class="font-medium">{{ o.odds || '—' }}</td>
              <td>{{ o.marketProb != null ? Math.round(o.marketProb * 100) + '%' : '—' }}</td>
              <td>{{ o.modelProb != null ? Math.round(o.modelProb * 100) + '%' : '—' }}</td>
            </tr>
          </tbody>
        </table>
        <template v-if="dogBox.reasons.length">
          <p class="mb-1 font-medium text-slate-800">{{ dogBox.headline }}</p>
          <ul class="space-y-1.5 mb-2">
            <li v-for="r in dogBox.reasons" :key="r.key + r.text">
              • {{ r.text }}
              <span class="block pl-3 text-xs text-slate-500">Lo que dicen los datos: {{ r.evidence }}</span>
            </li>
          </ul>
        </template>
        <p v-else class="mb-2">No hay ningún dato que diga que {{ dogBox.underdog }} tiene más opciones de las que dice la cuota: si dudas de {{ dogBox.favorite }}, apuesta menos, no al otro.</p>
        <p class="text-xs text-slate-600">{{ dogBox.note }}</p>
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
            <option value="LOW_CONFIDENCE">🔸 Baja confianza</option>
            <option value="CANCELLED">🚫 Anulada</option>
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

const pct = (x) => Math.round(x * 100)

const pointBox = computed(() => {
  if (!matchId.value || !matchesStore.latest) return null
  const m = matchesStore.latest.tennis?.find(x => x.matchId === matchId.value)
  const g = m?.gamesModel
  if (!g?.markets || m.status === 'FINISHED') return null
  const mk = g.markets
  const mw = m.oddsMarkets?.matchWinner
  let close = false
  if (mw?.p1 > 1 && mw?.p2 > 1) {
    const fair = (1 / mw.p1) / (1 / mw.p1 + 1 / mw.p2)
    close = fair >= 0.4 && fair <= 0.6
  }
  const scores = Object.entries(mk.setScores || {})
    .map(([key, p]) => {
      const [a, b] = key.split('-').map(Number)
      return { key, p, label: a > b ? `${m.player1} ${a}-${b}` : `${m.player2} ${b}-${a}`, pct: pct(p) }
    })
    .sort((x, y) => y.p - x.p)
  return {
    g,
    close,
    p1: m.player1,
    p2: m.player2,
    match1: pct(mk.matchP1),
    match2: 100 - pct(mk.matchP1),
    set1: pct(mk.set1P1),
    set2: 100 - pct(mk.set1P1),
    tiebreak: pct(g.tiebreak),
    decider: pct(g.decider),
    deciderLabel: g.bestOf === 5 ? '4 o 5 sets' : '3er set',
    scores
  }
})

const surfaceEs = { hard: 'cemento', clay: 'arcilla', grass: 'césped' }
const h2hBox = computed(() => {
  if (!matchId.value || !matchesStore.latest) return null
  const m = matchesStore.latest.tennis?.find(x => x.matchId === matchId.value)
  if (!m) return null
  return { p1: m.player1, p2: m.player2, h: m.h2hDetail?.meetings?.length ? m.h2hDetail : null }
})

const factorEs = {
  en_juego: 'en juego', lesion: 'lesión', fisico: 'físico', personal: 'personal', local: 'en casa', entrenador: 'entrenador',
  motivacion: 'motivación', calendario: 'calendario', otro: 'otro'
}
const impactClass = {
  negativo: 'bg-red-100 text-red-800',
  positivo: 'bg-green-100 text-green-800',
  incierto: 'bg-slate-100 text-slate-700'
}
const currentTennisMatch = computed(() =>
  matchId.value ? matchesStore.latest?.tennis?.find(x => x.matchId === matchId.value) : null
)
const newsPending = computed(() => {
  const m = currentTennisMatch.value
  return !!m && m.status === 'SCHEDULED' && !m.playerNews
})
const dogBox = computed(() => currentTennisMatch.value?.underdogCase || null)
const newsBox = computed(() => {
  const m = currentTennisMatch.value
  const n = m?.playerNews
  if (!n) return null
  const mins = Math.max(0, Math.round((Date.now() - new Date(n.fetchedAt).getTime()) / 60000))
  const ago = mins < 60 ? `hace ${mins} min` : `hace ${Math.round(mins / 60)} h`
  return {
    n,
    ago,
    sides: [
      { key: 'p1', name: m.player1, items: n.player1 || [], read: n.headlinesRead?.player1 ?? 0 },
      { key: 'p2', name: m.player2, items: n.player2 || [], read: n.headlinesRead?.player2 ?? 0 }
    ]
  }
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
  FAILED: 'fallidas',
  LOW_CONFIDENCE: 'de baja confianza',
  CANCELLED: 'anuladas'
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
  // A match from a later day (tomorrow's slate) must still be in range.
  const to = historyDateTo.value || (matchDate.value && matchDate.value > todayStr ? matchDate.value : todayStr)
  const status = historyStatus.value !== 'all' ? historyStatus.value : null
  predictionsStore.fetchHistory(historySport.value, from, to, status, currentPage.value, pageSize.value, matchId.value, historyName.value)
  if (matchId.value && matchDate.value) {
    // Name, point-model box and dates come from that day's matches.
    matchesStore.fetchByDate(matchDate.value)
  } else {
    matchesStore.fetchHistory(from, to, historySport.value, currentPage.value, pageSize.value)
  }
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
