<template>
  <div>
    <div class="mb-4">
      <router-link :to="backTo" class="text-blue-600 hover:underline text-sm">
        ← Volver a predicciones
      </router-link>
    </div>

    <h1 class="text-2xl font-bold text-slate-900 mb-6">Detalle de Predicción</h1>

    <div v-if="predictionsStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <div v-else-if="predictionsStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ predictionsStore.error }}
    </div>

    <div v-else-if="predictionsStore.detail" class="space-y-6">
      <!-- Header card -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 sm:p-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
          <div>
            <h3 class="text-sm font-medium text-slate-500 mb-1">Predicción</h3>
            <p class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.prediction.prediction }}</p>
          </div>
          <div>
            <h3 class="text-sm font-medium text-slate-500 mb-1">Mercado</h3>
            <p class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.prediction.market }}</p>
          </div>
          <div>
            <h3 class="text-sm font-medium text-slate-500 mb-1">Confianza</h3>
            <div class="flex items-center">
              <div class="w-24 bg-slate-200 rounded-full h-3 mr-3">
                <div class="bg-blue-600 h-3 rounded-full" :style="{ width: (predictionsStore.detail.prediction.calibratedConfidence ?? predictionsStore.detail.prediction.confidence) + '%' }"></div>
              </div>
              <span class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.prediction.calibratedConfidence ?? predictionsStore.detail.prediction.confidence }}%</span>
            </div>
          </div>
          <div>
            <h3 class="text-sm font-medium text-slate-500 mb-1">Estado</h3>
            <span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium"
              :class="getStatusClass(predictionsStore.detail.prediction.status)">
              {{ predictionsStore.detail.prediction.status }}
            </span>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200">
        <div class="border-b border-slate-200">
          <nav class="flex -mb-px overflow-x-auto" aria-label="Tabs">
            <button
              v-for="tab in [
                { key: 'simple', label: 'Explicación sencilla' },
                { key: 'stats', label: 'Justificación estadística' },
                { key: 'result', label: 'Resultado' },
                { key: 'live', label: 'Historial en vivo' }
              ]"
              :key="tab.key"
              @click="activeTab = tab.key"
              :class="[
                'px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap',
                activeTab === tab.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              ]"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>

        <div class="p-4 sm:p-6">
          <!-- Simple explanation -->
          <div v-if="activeTab === 'simple'" class="space-y-4">
            <h3 class="text-lg font-semibold text-slate-900">Explicación en lenguaje natural</h3>
            <p v-if="predictionsStore.detail.prediction.naturalLanguageReasoning" class="text-slate-700 leading-relaxed">
              {{ predictionsStore.detail.prediction.naturalLanguageReasoning }}
            </p>
            <div v-else class="bg-slate-50 rounded-lg p-4 text-slate-600">
              No hay una explicación en lenguaje natural disponible todavía. Ve a la pestaña
              <strong>Justificación estadística</strong> para ver los números detrás de la predicción.
            </div>

            <!-- What other sites say (external reference) -->
            <div v-if="expertInfo" class="bg-sky-50 border border-sky-200 rounded-lg p-4">
              <h4 class="text-sm font-semibold text-sky-900 mb-2">🌐 ¿Qué dicen otros sitios?</h4>
              <p class="text-slate-700 leading-relaxed">
                <strong>ClubElo</strong> es una página independiente que mide la fuerza de los equipos de fútbol
                con estadísticas (su propio ranking). Para este partido le da a
                <strong>{{ expertInfo.homeName }}</strong> un <strong>{{ expertInfo.homePct }}%</strong>
                de probabilidad de ganarle a <strong>{{ expertInfo.awayName }}</strong>
                ({{ expertInfo.awayPct }}%), sin contar el empate.
              </p>
              <p v-if="expertInfo.ourHomePct != null" class="text-slate-700 leading-relaxed mt-2">
                Nosotros le damos un <strong>{{ expertInfo.ourHomePct }}%</strong> a {{ expertInfo.homeName }}.
                <span v-if="expertInfo.agree" class="text-green-700 font-medium">Los dos coincidimos en el favorito. ✅</span>
                <span v-else class="text-amber-700 font-medium">Ojo: ellos ven favorito a {{ expertInfo.theirFavorite }} y nosotros a {{ expertInfo.ourFavorite }}. ⚠️</span>
              </p>
              <p class="text-xs text-slate-500 mt-3">
                Es solo una referencia: por ahora <strong>no cambia nuestra predicción</strong>. Estamos midiendo
                qué tan acertada es esta fuente antes de darle peso en el modelo.
              </p>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div class="bg-slate-50 rounded-lg p-4">
                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Predicción</h4>
                <p class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.prediction.prediction }}</p>
              </div>
              <div class="bg-slate-50 rounded-lg p-4">
                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Confianza</h4>
                <p class="text-lg font-semibold text-slate-900">
                  {{ predictionsStore.detail.prediction.calibratedConfidence ?? predictionsStore.detail.prediction.confidence }}%
                </p>
                <p v-if="predictionsStore.detail.prediction.calibratedConfidence != null && predictionsStore.detail.prediction.calibratedConfidence !== predictionsStore.detail.prediction.confidence" class="text-xs text-slate-500 mt-1">
                  Calibrada con resultados reales · modelo: {{ predictionsStore.detail.prediction.confidence }}%
                </p>
              </div>
              <div v-if="evValue != null" class="bg-slate-50 rounded-lg p-4 md:col-span-2">
                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Valor de la apuesta (Edge{{ usesCalibratedEv ? ' calibrado' : '' }})
                </h4>
                <div class="flex items-center gap-3 flex-wrap">
                  <span
                    class="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold"
                    :class="evClass"
                  >
                    {{ evPctText }}
                  </span>
                  <span v-if="stakePct" class="text-sm text-slate-700">
                    Stake sugerido: <strong>{{ stakePct }}%</strong> del bankroll (¼ Kelly)
                  </span>
                  <span class="text-xs text-slate-500">Regla: solo apostar con edge mayor a 5%</span>
                </div>
                <p v-if="usesCalibratedEv && predictionsStore.detail.prediction.expectedValue != null && predictionsStore.detail.prediction.expectedValue !== evValue" class="text-xs text-slate-500 mt-2">
                  Edge crudo del modelo: {{ (predictionsStore.detail.prediction.expectedValue * 100).toFixed(1) }}% · el edge calibrado usa la probabilidad ajustada con resultados reales.
                </p>
              </div>
            </div>
          </div>

          <!-- Statistical justification -->
          <div v-if="activeTab === 'stats'" class="space-y-6">
            <div>
              <h3 class="text-lg font-semibold text-slate-900 mb-3">¿Por qué esta confianza?</h3>
              <p class="text-slate-700 leading-relaxed">
                {{ predictionsStore.detail.prediction.reasoning || 'No hay justificación disponible para esta predicción.' }}
              </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <!-- Model contributions -->
              <div v-if="predictionsStore.detail.prediction.modelContributions && Object.keys(predictionsStore.detail.prediction.modelContributions).length">
                <h4 class="text-sm font-medium text-slate-500 mb-3">Peso de cada modelo</h4>
                <div class="space-y-3">
                  <div v-for="(value, key) in predictionsStore.detail.prediction.modelContributions" :key="key" class="flex items-center gap-2 sm:gap-3">
                    <span class="w-20 sm:w-28 text-sm text-slate-600 capitalize truncate">{{ formatKey(key) }}</span>
                    <div class="flex-1 mx-1 sm:mx-3 bg-slate-200 rounded-full h-3 min-w-0">
                      <div class="bg-emerald-500 h-3 rounded-full" :style="{ width: (value * 100) + '%' }"></div>
                    </div>
                    <span class="w-12 sm:w-14 text-right text-sm font-medium text-slate-900">{{ (value * 100).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>

              <!-- Probabilities -->
              <div v-if="predictionsStore.detail.prediction.probabilities && Object.keys(predictionsStore.detail.prediction.probabilities).length">
                <h4 class="text-sm font-medium text-slate-500 mb-3">Probabilidades calculadas</h4>
                <div class="space-y-3">
                  <div v-for="(value, key) in predictionsStore.detail.prediction.probabilities" :key="key" class="flex items-center gap-2 sm:gap-3">
                    <span class="w-20 sm:w-28 text-sm text-slate-600 capitalize truncate">{{ formatKey(key) }}</span>
                    <div class="flex-1 mx-1 sm:mx-3 bg-slate-200 rounded-full h-3 min-w-0">
                      <div class="bg-indigo-600 h-3 rounded-full" :style="{ width: (value * 100) + '%' }"></div>
                    </div>
                    <span class="w-12 sm:w-14 text-right text-sm font-medium text-slate-900">{{ (value * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Reasoning data visualized -->
            <div v-if="reasoningItems.length">
              <h3 class="text-lg font-semibold text-slate-900 mb-4">Datos utilizados</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div v-for="(item, idx) in reasoningItems" :key="idx" class="bg-slate-50 rounded-lg p-4">
                  <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">{{ item.label }}</h4>

                  <!-- Simple value -->
                  <p v-if="item.type === 'value'" class="text-lg font-semibold text-slate-900">{{ item.value }}</p>

                  <!-- Expected score or goals -->
                  <div v-else-if="item.type === 'score'" class="flex items-center justify-center gap-3 text-lg font-semibold text-slate-900">
                    <span>{{ item.home }}</span>
                    <span class="text-slate-400">-</span>
                    <span>{{ item.away }}</span>
                  </div>

                  <!-- Bar chart for nested probabilities -->
                  <div v-else-if="item.type === 'bars'" class="space-y-2">
                    <div v-for="(subValue, subKey) in item.values" :key="subKey" class="flex items-center">
                      <span class="w-20 text-xs text-slate-600 capitalize">{{ formatKey(subKey) }}</span>
                      <div class="flex-1 mx-2 bg-slate-200 rounded-full h-2">
                        <div class="h-2 rounded-full" :class="item.color" :style="{ width: normalizePercent(subValue) + '%' }"></div>
                      </div>
                      <span class="w-12 text-right text-xs font-medium text-slate-900">{{ formatPercent(subValue) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Surface stats (tennis) -->
            <div v-if="surfaceStatsPlayers.length" class="mt-6">
              <h3 class="text-lg font-semibold text-slate-900 mb-1">Rendimiento por superficie</h3>
              <p class="text-sm text-slate-500 mb-4">
                Historial del jugador en cada superficie (base de datos 2010+). Este partido se juega en
                <span class="font-medium text-slate-700">{{ surfaceLabel(surfaceStats.surface) }}</span>.
              </p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="player in surfaceStatsPlayers" :key="player.side" class="bg-slate-50 rounded-lg p-4">
                  <div class="flex items-center justify-between mb-3">
                    <h4 class="font-semibold text-slate-900">{{ player.name }}</h4>
                    <span v-if="player.eloOverall" class="text-xs text-slate-500">Elo {{ Math.round(player.eloOverall) }}</span>
                  </div>
                  <div class="space-y-2">
                    <div
                      v-for="surf in surfaceOrder"
                      :key="surf"
                      class="flex items-center gap-2 rounded-md px-2 py-1.5"
                      :class="surf === surfaceStats.surface ? 'bg-blue-100/70 ring-1 ring-blue-300' : ''"
                    >
                      <span class="w-28 text-xs text-slate-600 flex items-center gap-1">
                        {{ surfaceLabel(surf) }}
                        <span v-if="surf === surfaceStats.surface" class="text-[10px] font-semibold text-blue-700 uppercase">hoy</span>
                      </span>
                      <div class="flex-1 bg-slate-200 rounded-full h-2.5 min-w-0">
                        <div
                          class="h-2.5 rounded-full"
                          :class="surfaceBarColor(surf)"
                          :style="{ width: winPct(player, surf) + '%' }"
                        ></div>
                      </div>
                      <span class="w-32 text-right text-xs font-medium text-slate-900">{{ recordText(player, surf) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Tournament load (tennis) -->
            <div v-if="tournamentLoadPlayers.length" class="mt-6">
              <h3 class="text-lg font-semibold text-slate-900 mb-1">Carga en el torneo</h3>
              <p class="text-sm text-slate-500 mb-4">
                Partidos, sets y games que lleva cada jugador en {{ tournamentLoad.tournament || 'este torneo' }}
                antes de este partido. Más games acumulados = más desgaste físico.
              </p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="player in tournamentLoadPlayers" :key="player.side" class="bg-slate-50 rounded-lg p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h4 class="font-semibold text-slate-900">{{ player.name }}</h4>
                    <span
                      v-if="player.loadLevel"
                      class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                      :class="loadLevelBadgeClass(player.loadLevel)"
                    >
                      Carga {{ player.loadLevel }}
                    </span>
                  </div>
                  <div class="flex flex-wrap gap-2 mb-3 text-xs text-slate-600">
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">🎾 {{ player.matchesPlayed }} partidos</span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Sets: <strong>{{ player.setsWon }}-{{ player.setsLost }}</strong></span>
                    <span v-if="player.totalGames != null" class="px-2 py-1 rounded bg-white border border-slate-200">Games: <strong>{{ player.gamesWon }}-{{ player.gamesLost }}</strong></span>
                    <span v-if="player.pointsWon != null" class="px-2 py-1 rounded bg-white border border-slate-200">Puntos: <strong>{{ player.pointsWon }}-{{ player.pointsLost }}</strong></span>
                  </div>
                  <div v-if="player.loadPct != null" class="flex items-center gap-2">
                    <div class="flex-1 bg-slate-200 rounded-full h-2.5 min-w-0">
                      <div class="h-2.5 rounded-full" :class="loadBarClass(player.loadLevel)" :style="{ width: player.loadPct + '%' }"></div>
                    </div>
                    <span class="text-xs font-medium text-slate-700 whitespace-nowrap">{{ player.totalGames }} games</span>
                  </div>
                  <p v-else class="text-xs text-slate-400">Sin detalle de games todavía</p>
                </div>
              </div>
              <p v-if="loadDiffText" class="text-sm text-slate-600 mt-3">{{ loadDiffText }}</p>
              <p class="text-xs text-slate-400 mt-2">
                Los puntos por set solo están disponibles en partidos con estadísticas de la fuente (la mayoría recientes).
              </p>
            </div>

            <!-- Surface load & rest (tennis) -->
            <div v-if="surfaceLoadPlayers.length" class="mt-6">
              <h3 class="text-lg font-semibold text-slate-900 mb-1">Esfuerzo por superficie y descanso</h3>
              <p class="text-sm text-slate-500 mb-4">
                Games jugados en los últimos {{ surfaceLoad.windowDays }} días por superficie (cualquier torneo)
                y días de descanso desde el último partido. Menos descanso y más games = más fatiga.
              </p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="player in surfaceLoadPlayers" :key="player.side" class="bg-slate-50 rounded-lg p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h4 class="font-semibold text-slate-900">{{ player.name }}</h4>
                    <span
                      class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold"
                      :class="restBadgeClass(player.restDays)"
                    >
                      {{ restLabel(player.restDays) }}
                    </span>
                  </div>
                  <p v-if="player.lastMatchDate" class="text-xs text-slate-500 mb-3">
                    Último partido: {{ player.lastMatchDate }}<span v-if="player.lastMatchTournament"> · {{ player.lastMatchTournament }}</span><span v-if="player.lastMatchSurface"> · {{ surfaceLabel(player.lastMatchSurface) }}</span>
                  </p>
                  <div class="flex flex-wrap gap-2 text-xs text-slate-600">
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">🎾 {{ player.totalMatches }} partidos</span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Games: <strong>{{ player.totalGames }}</strong></span>
                  </div>
                  <div class="space-y-1.5 mt-3">
                    <template v-for="surf in surfaceOrder" :key="surf">
                      <div
                        v-if="player.surfaces && player.surfaces[surf]"
                        class="flex items-center gap-2 rounded-md px-2 py-1"
                        :class="surf === surfaceLoad.surface ? 'bg-blue-100/70 ring-1 ring-blue-300' : ''"
                      >
                        <span class="w-28 text-xs text-slate-600 flex items-center gap-1">
                          {{ surfaceLabel(surf) }}
                          <span v-if="surf === surfaceLoad.surface" class="text-[10px] font-semibold text-blue-700 uppercase">hoy</span>
                        </span>
                        <span class="text-xs text-slate-600">{{ player.surfaces[surf].matchesPlayed }} part.</span>
                        <span class="text-xs font-medium text-slate-900">
                          {{ player.surfaces[surf].totalGames != null ? player.surfaces[surf].totalGames + ' games' : 'sin detalle de games' }}
                        </span>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
            <!-- Serve/return & tiebreaks (tennis) -->
            <div v-if="serveStatsPlayers.length" class="mt-6">
              <h3 class="text-lg font-semibold text-slate-900 mb-1">Saque, resto y tiebreaks</h3>
              <p class="text-sm text-slate-500 mb-4">
                Promedios recientes (últimos 20 partidos con estadísticas): solidez al saque (hold),
                capacidad de quebrar (break) y rendimiento en tiebreaks.
              </p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div v-for="player in serveStatsPlayers" :key="player.side" class="bg-slate-50 rounded-lg p-4">
                  <h4 class="font-semibold text-slate-900 mb-2">{{ player.name }}</h4>
                  <div v-if="player.overall.serveMatches" class="flex flex-wrap gap-2 mb-3 text-xs text-slate-600">
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Hold: <strong>{{ pctText(player.overall.holdPct) }}</strong></span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Break: <strong>{{ pctText(player.overall.breakPct) }}</strong></span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">1er saque: <strong>{{ pctText(player.overall.firstServePct) }}</strong></span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Pts con 1ero: <strong>{{ pctText(player.overall.firstServeWonPct) }}</strong></span>
                    <span class="px-2 py-1 rounded bg-white border border-slate-200">Tiebreaks: <strong>{{ player.overall.tiebreaksWon }}-{{ player.overall.tiebreaksPlayed - player.overall.tiebreaksWon }}</strong></span>
                  </div>
                  <div class="space-y-1.5">
                    <template v-for="surf in surfaceOrder" :key="surf">
                      <div
                        v-if="player.bySurface && player.bySurface[surf]"
                        class="flex items-center gap-2 rounded-md px-2 py-1"
                        :class="surf === serveStats.surface ? 'bg-blue-100/70 ring-1 ring-blue-300' : ''"
                      >
                        <span class="w-28 text-xs text-slate-600 flex items-center gap-1">
                          {{ surfaceLabel(surf) }}
                          <span v-if="surf === serveStats.surface" class="text-[10px] font-semibold text-blue-700 uppercase">hoy</span>
                        </span>
                        <span class="text-xs text-slate-600">Hold <strong>{{ pctText(player.bySurface[surf].holdPct) }}</strong></span>
                        <span class="text-xs text-slate-600">Break <strong>{{ pctText(player.bySurface[surf].breakPct) }}</strong></span>
                        <span class="text-xs text-slate-400">({{ player.bySurface[surf].serveMatches }} part.)</span>
                      </div>
                    </template>
                  </div>
                  <p v-if="!player.overall.serveMatches" class="text-xs text-slate-400">Sin estadísticas de saque todavía</p>
                </div>
              </div>
            </div>
          </div>
          <div v-if="activeTab === 'result'">
            <div v-if="predictionsStore.detail.result" class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 class="text-sm font-medium text-slate-500 mb-1">Resultado Real</h4>
                <p class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.result.actualResult }}</p>
              </div>
              <div>
                <h4 class="text-sm font-medium text-slate-500 mb-1">¿Acertado?</h4>
                <span class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium"
                  :class="predictionsStore.detail.result.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
                  {{ predictionsStore.detail.result.success ? '✅ SÍ' : '❌ NO' }}
                </span>
              </div>
              <div class="md:col-span-2">
                <h4 class="text-sm font-medium text-slate-500 mb-1">Justificación</h4>
                <p class="text-slate-700">{{ predictionsStore.detail.result.validationReason }}</p>
              </div>
              <div v-if="predictionsStore.detail.result.matchScore">
                <h4 class="text-sm font-medium text-slate-500 mb-1">Marcador final</h4>
                <p class="text-lg font-semibold text-slate-900">{{ predictionsStore.detail.result.matchScore }}</p>
              </div>
            </div>
            <div v-else class="text-slate-500">
              Resultado pendiente de validación.
            </div>
          </div>

          <!-- Live history -->
          <div v-if="activeTab === 'live'" class="space-y-6">
            <h3 class="text-lg font-semibold text-slate-900">Historial de actualizaciones parciales</h3>

            <!-- Current partial score -->
            <div v-if="latestSnapshot" class="bg-blue-50 border border-blue-100 rounded-lg p-5">
              <h4 class="text-sm font-semibold text-blue-800 mb-3">Resultado parcial actual</h4>
              <div class="flex flex-wrap items-center gap-6">
                <div class="text-center">
                  <div class="text-xs text-blue-600 uppercase tracking-wider">Marcador</div>
                  <div class="text-3xl font-bold text-blue-900">
                    {{ latestSnapshot.homeScore }} - {{ latestSnapshot.awayScore }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-xs text-blue-600 uppercase tracking-wider">Tiempo</div>
                  <div class="text-xl font-semibold text-blue-900">
                    {{ latestSnapshot.periodLabel || `${latestSnapshot.minute}'` }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-xs text-blue-600 uppercase tracking-wider">Cumplimiento</div>
                  <div class="text-xl font-semibold text-blue-900">
                    {{ latestSnapshot.fulfillmentPercent.toFixed(1) }}%
                  </div>
                </div>
                <div v-if="latestSnapshot.snapshotAt" class="text-sm text-blue-700">
                  Actualizado: {{ formatDateTimeIso(latestSnapshot.snapshotAt) }}
                </div>
              </div>
            </div>

            <div v-if="predictionsStore.progress && predictionsStore.progress.snapshots.length" class="overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead class="bg-slate-50 text-slate-600">
                  <tr>
                    <th class="px-3 py-2 text-left">Tiempo</th>
                    <th class="px-3 py-2 text-left">Marcador</th>
                    <th class="px-3 py-2 text-left">Cumplimiento</th>
                    <th class="px-3 py-2 text-left">Hora actualización</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(snap, idx) in predictionsStore.progress.snapshots" :key="idx" class="border-b border-slate-100">
                    <td class="px-3 py-2 font-medium">{{ snap.periodLabel || `${snap.minute}'` }}</td>
                    <td class="px-3 py-2 font-medium">{{ snap.homeScore }} - {{ snap.awayScore }}</td>
                    <td class="px-3 py-2">
                      <div class="flex items-center">
                        <div class="w-24 bg-slate-200 rounded-full h-2 mr-2">
                          <div class="h-2 rounded-full" :class="fulfillmentClass(snap.fulfillmentPercent)" :style="{ width: snap.fulfillmentPercent + '%' }"></div>
                        </div>
                        <span class="font-medium">{{ snap.fulfillmentPercent.toFixed(1) }}%</span>
                      </div>
                    </td>
                    <td class="px-3 py-2 text-slate-500">
                      {{ snap.snapshotAt ? formatDateTimeIso(snap.snapshotAt) : '-' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else class="text-slate-500">
              Aún no hay actualizaciones parciales registradas para esta predicción. Cuando el partido esté en vivo y se actualicen los marcadores, aparecerán aquí.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { usePredictionsStore } from '../stores/predictions.js'
import { formatDateTimeIso } from '../utils/format.js'

const route = useRoute()

const backTo = computed(() => {
  const query = {}
  if (route.query.matchId) query.matchId = route.query.matchId
  if (route.query.date) query.date = route.query.date
  return { path: '/predictions', query }
})

const props = defineProps({
  id: {
    type: String,
    required: true
  }
})

const predictionsStore = usePredictionsStore()
const activeTab = ref('simple')

const latestSnapshot = computed(() => {
  const snapshots = predictionsStore.progress?.snapshots || []
  return snapshots.length ? snapshots[snapshots.length - 1] : null
})

const surfaceStats = computed(() => predictionsStore.surfaceStats)
const surfaceStatsPlayers = computed(() => predictionsStore.surfaceStats?.players || [])
const surfaceOrder = ['clay', 'hard', 'grass']

const tournamentLoad = computed(() => predictionsStore.tournamentLoad)
const tournamentLoadPlayers = computed(() => predictionsStore.tournamentLoad?.players || [])

const loadDiffText = computed(() => {
  const ps = predictionsStore.tournamentLoad?.players || []
  if (ps.length !== 2 || ps[0].totalGames == null || ps[1].totalGames == null) return null
  const diff = ps[0].totalGames - ps[1].totalGames
  if (diff === 0) return 'Los dos llegan con la misma carga de games.'
  const more = diff > 0 ? ps[0] : ps[1]
  const less = diff > 0 ? ps[1] : ps[0]
  return `${more.name} llega con ${Math.abs(diff)} games más de carga que ${less.name} (${more.totalGames} vs ${less.totalGames}).`
})

function loadLevelBadgeClass(level) {
  return {
    leve: 'bg-green-100 text-green-800',
    media: 'bg-yellow-100 text-yellow-800',
    alta: 'bg-red-100 text-red-800'
  }[level] || 'bg-slate-100 text-slate-800'
}

function loadBarClass(level) {
  return { leve: 'bg-green-500', media: 'bg-yellow-500', alta: 'bg-red-500' }[level] || 'bg-slate-500'
}

const surfaceLoad = computed(() => predictionsStore.surfaceLoad)
const surfaceLoadPlayers = computed(() => predictionsStore.surfaceLoad?.players || [])

function restBadgeClass(days) {
  if (days == null) return 'bg-slate-100 text-slate-800'
  if (days <= 1) return 'bg-red-100 text-red-800'
  if (days === 2) return 'bg-yellow-100 text-yellow-800'
  return 'bg-green-100 text-green-800'
}

function restLabel(days) {
  if (days == null) return 'Sin partidos previos'
  if (days === 0) return 'Juega hoy también'
  return days === 1 ? '1 día de descanso' : `${days} días de descanso`
}

const serveStats = computed(() => predictionsStore.serveStats)
const serveStatsPlayers = computed(() => predictionsStore.serveStats?.players || [])

function pctText(v) {
  return v == null ? '-' : Math.round(v * 100) + '%'
}

const evValue = computed(() => {
  const p = predictionsStore.detail?.prediction
  return p?.calibratedExpectedValue ?? p?.expectedValue ?? null
})
const usesCalibratedEv = computed(() => predictionsStore.detail?.prediction?.calibratedExpectedValue != null)
const evPctText = computed(() => {
  if (evValue.value == null) return '-'
  const pct = evValue.value * 100
  return (pct > 0 ? '+' : '') + pct.toFixed(1) + '%'
})
const evClass = computed(() => {
  if (evValue.value == null) return 'bg-slate-100 text-slate-800'
  if (evValue.value >= 0.05) return 'bg-green-100 text-green-800'
  if (evValue.value >= 0) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
})
const stakePct = computed(() => {
  const k = predictionsStore.detail?.prediction?.kellyFraction
  if (k == null || k <= 0) return null
  // Fracción de Kelly conservadora: 1/4 del Kelly completo
  return ((k / 4) * 100).toFixed(1)
})

// External consensus (ClubElo) shown in plain language
const expertInfo = computed(() => {
  const pred = predictionsStore.detail?.prediction
  const ec = pred?.reasoningData?.expertConsensus
  if (!ec || ec.homeWinPct == null || ec.awayWinPct == null) return null
  const homeName = ec.homeTeam || 'Local'
  const awayName = ec.awayTeam || 'Visitante'
  const ourHomeProb = pred?.probabilities?.home
  const ourHomePct = typeof ourHomeProb === 'number' ? Math.round(ourHomeProb * 100) : null
  const theirFavorite = ec.homeWinPct >= ec.awayWinPct ? homeName : awayName
  let ourFavorite = null
  let agree = null
  if (ourHomePct != null && pred?.probabilities?.away != null) {
    ourFavorite = ourHomeProb >= pred.probabilities.away ? homeName : awayName
    agree = ourFavorite === theirFavorite
  }
  return {
    homeName,
    awayName,
    homePct: ec.homeWinPct,
    awayPct: ec.awayWinPct,
    ourHomePct,
    theirFavorite,
    ourFavorite,
    agree
  }
})

function surfaceLabel(s) {
  return { clay: 'Polvo de ladrillo', hard: 'Cemento', grass: 'Césped' }[s] || s || 'Desconocida'
}

function surfaceBarColor(s) {
  return { clay: 'bg-orange-500', hard: 'bg-blue-500', grass: 'bg-green-500' }[s] || 'bg-slate-500'
}

function surfaceAgg(player, surf) {
  return player?.surfaces?.[surf] || null
}

function winPct(player, surf) {
  const agg = surfaceAgg(player, surf)
  return agg && agg.played ? Math.round(agg.win_rate * 100) : 0
}

function recordText(player, surf) {
  const agg = surfaceAgg(player, surf)
  if (!agg || !agg.played) return 'Sin datos'
  const pct = Math.round(agg.win_rate * 100)
  const elo = player.eloBySurface?.[surf]
  return `${pct}% (${agg.wins}-${agg.losses})` + (elo ? ` · Elo ${Math.round(elo)}` : '')
}

const reasoningItems = computed(() => {
  const data = predictionsStore.detail?.prediction?.reasoningData
  if (!data || typeof data !== 'object') return []

  const items = []

  // Model badge
  if (data.model) {
    items.push({ label: 'Modelo principal', type: 'value', value: formatKey(String(data.model)) })
  }

  // Expected score
  if (data.expectedScore) {
    const parts = String(data.expectedScore).split(/[-:]/)
    if (parts.length >= 2) {
      items.push({ label: 'Marcador esperado', type: 'score', home: parts[0].trim(), away: parts[1].trim() })
    } else {
      items.push({ label: 'Marcador esperado', type: 'value', value: data.expectedScore })
    }
  }

  // Expected goals (single values)
  if (data.expectedHomeGoals != null && data.expectedAwayGoals != null) {
    items.push({
      label: 'Goles esperados',
      type: 'score',
      home: Number(data.expectedHomeGoals).toFixed(2),
      away: Number(data.expectedAwayGoals).toFixed(2)
    })
  }

  // Nested probability objects
  const nestedColors = {
    elo: 'bg-blue-500',
    poisson: 'bg-pink-500',
    xgboost: 'bg-purple-500',
    catboost: 'bg-orange-500'
  }

  for (const [key, value] of Object.entries(data)) {
    if (key === 'model' || key === 'expectedScore' || key === 'expertConsensus') continue
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const numericValues = Object.fromEntries(
        Object.entries(value).filter(([, v]) => typeof v === 'number')
      )
      if (Object.keys(numericValues).length) {
        items.push({
          label: `Probabilidades ${formatKey(key)}`,
          type: 'bars',
          values: numericValues,
          color: nestedColors[key] || 'bg-slate-500'
        })
      }
    } else if (typeof value === 'number') {
      items.push({ label: formatKey(key), type: 'value', value: Number(value).toFixed(3) })
    }
  }

  return items
})

function normalizePercent(value) {
  const num = typeof value === 'number' ? value : parseFloat(value)
  if (isNaN(num)) return 0
  // If already a probability (0-1), scale to 100
  return num <= 1 ? num * 100 : Math.min(num, 100)
}

function formatPercent(value) {
  const num = typeof value === 'number' ? value : parseFloat(value)
  if (isNaN(num)) return '-'
  return (num <= 1 ? num * 100 : num).toFixed(1) + '%'
}

function fulfillmentClass(value) {
  if (value >= 70) return 'bg-green-500'
  if (value >= 40) return 'bg-yellow-500'
  return 'bg-red-500'
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

function formatKey(key) {
  return key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim()
}

onMounted(() => {
  predictionsStore.surfaceStats = null
  predictionsStore.tournamentLoad = null
  predictionsStore.surfaceLoad = null
  predictionsStore.serveStats = null
  predictionsStore.fetchDetail(props.id).then(() => {
    const p = predictionsStore.detail?.prediction
    if (p?.sport === 'tennis' && p?.matchId) {
      predictionsStore.fetchSurfaceStats(p.matchId)
      predictionsStore.fetchTournamentLoad(p.matchId)
      predictionsStore.fetchSurfaceLoad(p.matchId)
      predictionsStore.fetchServeStats(p.matchId)
    }
  })
  predictionsStore.fetchProgress(props.id)
})
</script>
