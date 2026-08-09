<template>
  <div class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-slate-200">
        <thead class="bg-slate-50">
          <tr>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Mercado</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Predicción</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Confianza</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Edge</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider hidden sm:table-cell">Modelos</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider hidden md:table-cell">Fecha Partido</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Estado</th>
            <th class="px-3 sm:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider">Acción</th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-slate-200">
          <template v-for="group in groupedByMatch" :key="group.matchId">
            <!-- Match header row -->
            <tr class="bg-slate-100">
              <td colspan="8" class="px-3 sm:px-6 py-3">
                <div class="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 min-w-0">
                  <span class="inline-flex self-start items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                    :class="group.sport === 'tennis' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'">
                    {{ group.sport === 'tennis' ? '🎾 Tenis' : '⚽ Fútbol' }}
                  </span>
                  <span class="text-sm font-semibold text-slate-800 truncate">
                    {{ getMatchName(group) }}
                  </span>
                  <span class="text-xs text-slate-500 hidden sm:inline">
                    ({{ group.matchId }})
                  </span>
                </div>
              </td>
            </tr>
            <!-- Prediction rows for this match -->
            <tr v-for="pred in group.predictions" :key="pred.predictionId" class="hover:bg-slate-50">
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-slate-600">
                {{ pred.market }}
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm font-medium text-slate-900">
                {{ pred.prediction }}
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-slate-600 whitespace-nowrap">
                <div class="flex items-center" :title="pred.calibratedConfidence != null ? `Cruda (modelo): ${pred.confidence}% · Calibrada con resultados reales` : ''">
                  <div class="w-12 sm:w-16 bg-slate-200 rounded-full h-2 mr-2">
                    <div class="bg-blue-600 h-2 rounded-full" :style="{ width: (pred.calibratedConfidence ?? pred.confidence) + '%' }"></div>
                  </div>
                  <span class="text-sm font-medium">{{ pred.calibratedConfidence ?? pred.confidence }}%</span>
                  <span v-if="pred.calibratedConfidence != null && pred.calibratedConfidence !== pred.confidence" class="ml-1 text-[10px] text-slate-400">cal</span>
                </div>
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm whitespace-nowrap">
                <span
                  v-if="edgeOf(pred) != null"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                  :class="edgeClass(edgeOf(pred))"
                  :title="edgeTitle(pred)"
                >
                  {{ formatEdge(edgeOf(pred)) }}
                </span>
                <span v-else class="text-xs text-slate-400">-</span>
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-slate-600 hidden sm:table-cell">
                <div v-if="pred.modelContributions" class="flex items-center gap-1 w-24 sm:w-32">
                  <div class="flex-1 flex h-2 rounded-full overflow-hidden bg-slate-200">
                    <div v-for="(value, key) in pred.modelContributions" :key="key"
                      class="h-full"
                      :class="getModelColor(key)"
                      :style="{ width: (value * 100) + '%' }"
                      :title="`${formatKey(key)}: ${(value * 100).toFixed(0)}%`">
                    </div>
                  </div>
                </div>
                <span v-else class="text-xs text-slate-400">-</span>
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-slate-600 hidden md:table-cell whitespace-nowrap">
                {{ pred.eventDate ? formatDateTime(pred.eventDate, null) : getMatchDate(pred.matchId) }}
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-slate-600 whitespace-nowrap">
                <span class="inline-flex items-center px-2 py-0.5 sm:px-2.5 sm:py-0.5 rounded-full text-xs font-medium"
                  :class="getStatusClass(pred.status)">
                  {{ pred.status }}
                </span>
              </td>
              <td class="px-3 sm:px-6 py-3 sm:py-4 text-sm text-blue-600 whitespace-nowrap">
                <router-link :to="{ path: `/predictions/${pred.predictionId}`, query: detailQuery }" class="hover:underline">
                  Ver detalle
                </router-link>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { formatDateTime } from '../utils/format.js'

const route = useRoute()

const detailQuery = computed(() => {
  const query = {}
  if (route.query.matchId) query.matchId = route.query.matchId
  if (route.query.date) query.date = route.query.date
  return query
})

const props = defineProps({
  predictions: {
    type: Array,
    required: true
  },
  generatedAt: {
    type: String,
    default: null
  },
  matches: {
    type: Object,
    default: null
  }
})

const groupedByMatch = computed(() => {
  const groups = {}
  props.predictions.forEach(pred => {
    if (!groups[pred.matchId]) {
      groups[pred.matchId] = {
        matchId: pred.matchId,
        sport: pred.sport,
        predictions: []
      }
    }
    groups[pred.matchId].predictions.push(pred)
  })
  return Object.values(groups).sort((a, b) => {
    if (a.sport !== b.sport) {
      return a.sport.localeCompare(b.sport)
    }
    return a.matchId.localeCompare(b.matchId)
  })
})

function formatDate(dateStr) {
  if (!dateStr) return 'N/A'
  return new Date(`${dateStr}T00:00:00Z`).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC'
  })
}

function getMatchName(group) {
  // Prefer competitor names embedded in the prediction rows (server-side);
  // fall back to looking the match up in the loaded matches page.
  const first = group.predictions?.[0]
  if (first?.homeName && first?.awayName) {
    return `${first.homeName} vs ${first.awayName}`
  }
  const matchId = group.matchId
  if (!props.matches) return matchId
  const tennisMatch = props.matches.tennis?.find(m => m.matchId === matchId)
  if (tennisMatch) {
    return `${tennisMatch.player1} vs ${tennisMatch.player2}`
  }
  const footballMatch = props.matches.football?.find(m => m.matchId === matchId)
  if (footballMatch) {
    return `${footballMatch.homeTeam} vs ${footballMatch.awayTeam}`
  }
  return matchId
}

function getMatchDate(matchId) {
  if (!props.matches) return 'N/A'
  const tennisMatch = props.matches.tennis?.find(m => m.matchId === matchId)
  if (tennisMatch && tennisMatch.eventDate) {
    return formatDateTime(tennisMatch.eventDate, tennisMatch.eventTime)
  }
  const footballMatch = props.matches.football?.find(m => m.matchId === matchId)
  if (footballMatch && footballMatch.eventDate) {
    return formatDateTime(footballMatch.eventDate, footballMatch.eventTime)
  }
  return 'N/A'
}

function getStatusClass(status) {
  switch (status) {
    case 'PENDING': return 'bg-yellow-100 text-yellow-800'
    case 'LOW_CONFIDENCE': return 'bg-orange-100 text-orange-800'
    case 'VALIDATED': return 'bg-green-100 text-green-800'
    case 'FAILED': return 'bg-red-100 text-red-800'
    default: return 'bg-slate-100 text-slate-800'
  }
}

function edgeClass(ev) {
  if (ev >= 0.05) return 'bg-green-100 text-green-800'
  if (ev >= 0) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function edgeOf(pred) {
  // Prefer the calibrated edge (probability adjusted with real outcomes);
  // fall back to the raw model edge.
  return pred.calibratedExpectedValue ?? pred.expectedValue ?? null
}

function formatEdge(ev) {
  const pct = ev * 100
  return (pct > 0 ? '+' : '') + pct.toFixed(1) + '%'
}

function edgeTitle(pred) {
  const ev = edgeOf(pred)
  const parts = []
  if (pred.calibratedExpectedValue != null && pred.expectedValue != null && pred.calibratedExpectedValue !== pred.expectedValue) {
    parts.push(`Edge calibrado: ${(ev * 100).toFixed(1)}% (crudo: ${(pred.expectedValue * 100).toFixed(1)}%)`)
  } else {
    parts.push(`Edge: ${(ev * 100).toFixed(1)}% (prob x cuota - 1)`)
  }
  if (pred.kellyFraction != null && pred.kellyFraction > 0) {
    parts.push(`Kelly: ${(pred.kellyFraction * 100).toFixed(1)}% bankroll`)
  }
  if (ev < 0.05) {
    parts.push('Edge < 5%: no apostar')
  }
  return parts.join(' | ')
}

function formatKey(key) {
  return key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim()
}

function getModelColor(key) {
  const colors = {
    elo: 'bg-blue-500',
    surface_elo: 'bg-green-500',
    xgboost: 'bg-purple-500',
    catboost: 'bg-orange-500',
    poisson: 'bg-pink-500',
    ensemble: 'bg-indigo-500'
  }
  return colors[key] || 'bg-slate-500'
}
</script>
