<template>
  <router-link
    :to="{ path: '/predictions', query: { matchId: match.matchId, date: match.eventDate } }"
    class="block bg-white rounded-lg shadow-sm border border-slate-200 p-4 hover:border-blue-400 hover:shadow-md transition-all cursor-pointer"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="flex-1 min-w-0">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-2">
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-sm font-medium text-slate-500 flex-shrink-0">{{ sport === 'tennis' ? '🎾' : '⚽' }}</span>
            <span class="text-sm font-medium text-slate-500 truncate">{{ match.tournament || match.league }}</span>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <span
              v-if="bestConfidence != null"
              :class="isTop
                ? 'bg-orange-100 text-orange-700 border border-orange-300'
                : 'bg-green-100 text-green-700 border border-green-200'"
              class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap"
              :title="isTop ? 'Top 3: mayor confianza del día' : 'Confianza de la mejor predicción'"
            >
              {{ isTop ? '🔥' : '🎯' }} {{ bestConfidence }}%
            </span>
            <span
              v-else
              class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200 whitespace-nowrap"
              title="Este partido aún no tiene predicción generada"
            >
              ⏳ Sin predicción
            </span>
            <span v-if="match.eventDate" class="inline-flex items-center self-start px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 whitespace-nowrap">
              📅 {{ formatDateTime(match.eventDate, match.eventTime) }}
            </span>
          </div>
        </div>
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-3">
          <div class="text-base sm:text-lg font-semibold text-slate-900 truncate">
            {{ sport === 'tennis' ? match.player1 : match.homeTeam }}
          </div>
          <div class="text-sm text-slate-500 px-0 sm:px-3 flex-shrink-0">vs</div>
          <div class="text-base sm:text-lg font-semibold text-slate-900 truncate">
            {{ sport === 'tennis' ? match.player2 : match.awayTeam }}
          </div>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span v-if="match.eventTime && match.eventTime !== '00:00'" class="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-100">
            🕒 {{ formatTime(match.eventTime) }}
          </span>
          <span v-else-if="match.eventDate" class="text-slate-400">Hora por confirmar</span>
          <span v-if="sport === 'tennis' && match.surface" class="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-100">🏟️ {{ match.surface }}</span>
          <span v-if="sport === 'tennis' && match.rankingPlayer1" class="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-100">Ranking: #{{ match.rankingPlayer1 }} vs #{{ match.rankingPlayer2 }}</span>
          <span v-if="sport === 'football' && match.homePosition" class="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-100">Pos: {{ match.homePosition }} vs {{ match.awayPosition }}</span>
        </div>
      </div>
    </div>
  </router-link>
</template>

<script setup>
import { formatDateTime, formatDate, formatTime } from '../utils/format.js'

defineProps({
  match: {
    type: Object,
    required: true
  },
  sport: {
    type: String,
    required: true
  },
  bestConfidence: {
    type: Number,
    default: null
  },
  isTop: {
    type: Boolean,
    default: false
  }
})
</script>
