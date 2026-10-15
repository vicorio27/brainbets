<template>
  <div>
    <div class="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 mb-4">
      <h1 class="text-2xl font-bold text-slate-900">Dashboard</h1>
      <div class="flex items-center gap-3">
        <span class="text-xs text-slate-500 text-right">
          <span v-if="dash">
            Collect {{ ago(dash.lastMatchesUpdate) }} · Predict {{ ago(dash.lastPredictionsUpdate) }} · Validate {{ ago(dash.lastResultsUpdate) }}<br />
          </span>
          Cargado {{ lastLoadedAt ? fmtClock(lastLoadedAt) : '—' }}
        </span>
        <button
          @click="refresh"
          :disabled="refreshing"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-60"
        >
          <span :class="{ 'animate-spin': refreshing }">↻</span>
          {{ refreshing ? 'Actualizando…' : 'Actualizar' }}
        </button>
      </div>
    </div>

    <!-- Pick of the day: always the best edge available, coloured by how good it is -->
    <div
      v-if="pickOfDay"
      class="rounded-2xl p-5 sm:p-6 mb-6 shadow-lg bg-gradient-to-br"
      :class="POD_STYLE[pickOfDay.level].card"
    >
      <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider" :class="POD_STYLE[pickOfDay.level].sub">
        <span aria-hidden="true">{{ POD_STYLE[pickOfDay.level].icon }}</span>
        {{ POD_STYLE[pickOfDay.level].title }}
      </div>
      <div class="mt-2 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
        <div class="min-w-0">
          <div class="text-2xl sm:text-3xl font-bold leading-tight">
            {{ pickOfDay.market }} — {{ pickOfDay.prediction }}
          </div>
          <div class="text-sm mt-1" :class="POD_STYLE[pickOfDay.level].sub">
            {{ pickOfDay.home }} <span class="opacity-70">vs</span> {{ pickOfDay.away }}
            <span v-if="pickOfDay.tournament"> · {{ pickOfDay.tournament }}</span>
            <span v-if="pickOfDay.time && pickOfDay.time !== '00:00'"> · {{ pickOfDay.time }}</span>
          </div>
          <div class="text-sm mt-1.5 max-w-3xl" :class="POD_STYLE[pickOfDay.level].sub">{{ pickOfDay.why }}</div>
        </div>
        <div class="flex gap-5 sm:gap-6 flex-shrink-0">
          <div>
            <div class="text-2xl sm:text-3xl font-bold">{{ formatEdge(pickOfDay.edge) }}</div>
            <div class="text-[11px] uppercase tracking-wide" :class="POD_STYLE[pickOfDay.level].sub">edge</div>
          </div>
          <div>
            <div class="text-2xl sm:text-3xl font-bold">{{ pickOfDay.odd.toFixed(2) }}</div>
            <div class="text-[11px] uppercase tracking-wide" :class="POD_STYLE[pickOfDay.level].sub">cuota</div>
          </div>
          <div>
            <div class="text-2xl sm:text-3xl font-bold">{{ Math.round(pickOfDay.prob * 100) }}%</div>
            <div class="text-[11px] uppercase tracking-wide" :class="POD_STYLE[pickOfDay.level].sub">prob</div>
          </div>
          <div>
            <div class="text-2xl sm:text-3xl font-bold">{{ pickOfDay.kelly > 0 ? (pickOfDay.kelly * 25).toFixed(1) + '%' : '0%' }}</div>
            <div class="text-[11px] uppercase tracking-wide" :class="POD_STYLE[pickOfDay.level].sub">{{ pickOfDay.kelly > 0 ? '¼ Kelly' : 'stake sugerido' }}</div>
          </div>
        </div>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <router-link
          :to="pickOfDay.link"
          class="inline-flex items-center gap-1 text-sm font-medium rounded-lg px-3 py-1.5" :class="POD_STYLE[pickOfDay.level].btn"
        >Ver detalle →</router-link>
        <button
          @click="activeTab = 'bets'"
          class="inline-flex items-center gap-1 text-sm font-medium rounded-lg px-3 py-1.5" :class="POD_STYLE[pickOfDay.level].btn"
        >Más apuestas</button>
      </div>
    </div>
    <div
      v-else
      class="rounded-2xl border border-slate-200 bg-white p-5 mb-6 text-sm text-slate-500"
    >
      <span class="font-semibold text-slate-700">🏆 Apuesta del día:</span>
      no queda ningún partido de hoy por empezar que tenga cuota.
    </div>

    <!-- Tabs -->
    <div class="border-b border-slate-200 mb-6">
      <nav class="-mb-px flex gap-6 overflow-x-auto" aria-label="Tabs">
        <button
          v-for="t in tabs"
          :key="t.id"
          @click="activeTab = t.id"
          :class="activeTab === t.id
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'"
          class="whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm"
        >
          {{ t.label }}
        </button>
      </nav>
    </div>

    <div v-if="matchesStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
      <p class="mt-4 text-slate-600">Cargando datos...</p>
    </div>

    <div v-else-if="matchesStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ matchesStore.error }}
    </div>

    <!-- Reliability view: per-player / per-surface hit rate of each market -->
    <div v-else-if="activeTab === 'reliability'">
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-4">
        <h2 class="text-lg font-semibold text-slate-900">📊 Fiabilidad por jugador y superficie</h2>
        <p class="text-sm text-slate-500 mt-1">
          De todas nuestras predicciones ya validadas de tenis, qué mercado acierta más y cuál menos
          para cada jugador en cada superficie. El partido cuenta para ambos jugadores.
        </p>
        <div class="mt-3 relative sm:w-80">
          <input
            v-model="reliabilitySearch"
            type="text"
            list="reliability-players"
            aria-label="Buscar jugador"
            placeholder="Buscar jugador… (ej. Norrie, Medvedev)"
            @focus="searchFocused = true"
            @blur="onSearchBlur"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <datalist id="reliability-players">
            <option v-for="name in allPlayerNames" :key="name" :value="name" />
          </datalist>
          <!-- Full list on focus (empty query) so you can browse who's available -->
          <div
            v-if="searchFocused && !reliabilitySearch.trim() && allPlayerNames.length"
            class="absolute z-10 mt-1 w-full max-h-64 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg"
          >
            <button
              v-for="name in allPlayerNames"
              :key="name"
              type="button"
              @mousedown.prevent="pickPlayer(name)"
              class="block w-full text-left px-3 py-1.5 text-sm text-slate-700 hover:bg-blue-50"
            >
              {{ name }}
            </button>
          </div>
        </div>
        <p class="text-xs text-slate-500 mt-2">
          <b>{{ allPlayerNames.length }}</b> jugadores con datos disponibles.
          Muestra mínima para marcar "mejor/peor": {{ reliabilityMinSample }} predicciones.
          Con pocas semanas de historial las muestras por jugador aún son pequeñas — mira el <code>n</code>.
        </p>
      </div>

      <!-- Career record + Elo per surface, any player in the historical base -->
      <div v-if="reliabilitySearch.trim().length >= 2" class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-4">
        <h3 class="font-semibold text-slate-900 mb-1">Rendimiento por superficie (histórico)</h3>
        <p class="text-xs text-slate-500 mb-3">
          Récord de victorias y derrotas y Elo actual en cada superficie, sobre todos los partidos terminados
          de la base (desde 2010). Incluye jugadores sin partido hoy.
        </p>
        <p v-if="careerLoading && !surfaceCareerPlayers.length" class="text-sm text-slate-500">Buscando…</p>
        <div class="space-y-4">
          <div v-for="p in surfaceCareerPlayers" :key="p.name" class="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
            <div class="flex flex-wrap items-baseline gap-x-3 mb-2">
              <span class="font-medium text-slate-900">🎾 {{ p.name }}</span>
              <span class="text-xs text-slate-500">
                {{ p.wins }}-{{ p.losses }} en {{ p.played }} partidos<span v-if="p.eloOverall"> · Elo general {{ Math.round(p.eloOverall) }}</span>
              </span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div v-for="surf in ['hard', 'clay', 'grass']" :key="surf" class="text-sm">
                <div class="flex justify-between text-slate-700 mb-1">
                  <span>{{ surfaceLabel(surf) }}</span>
                  <span v-if="p.surfaces[surf]" class="font-semibold">{{ Math.round(p.surfaces[surf].win_rate * 100) }}%</span>
                  <span v-else class="text-xs text-slate-500">sin partidos</span>
                </div>
                <div class="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                  <div class="h-full rounded-full" :class="SURFACE_BAR[surf]" :style="{ width: (p.surfaces[surf] ? p.surfaces[surf].win_rate * 100 : 0) + '%' }"></div>
                </div>
                <div class="text-xs text-slate-500 mt-1">
                  <template v-if="p.surfaces[surf]">
                    {{ p.surfaces[surf].wins }}-{{ p.surfaces[surf].losses }}
                    · sets {{ p.surfaces[surf].sets_won }}-{{ p.surfaces[surf].sets_lost }}
                  </template>
                  <span v-if="p.eloBySurface[surf]"> · Elo {{ Math.round(p.eloBySurface[surf]) }}</span>
                </div>
              </div>
            </div>

            <!-- Playing profile: serve / return / tiebreaks vs the rest of the tour -->
            <div v-if="p.profile && p.profile.matches" class="mt-3 pt-3 border-t border-slate-100">
              <div class="flex flex-wrap items-center gap-2 mb-2">
                <span class="text-sm font-medium text-slate-700">Perfil de juego</span>
                <span
                  v-for="t in p.profile.tags"
                  :key="t.label"
                  class="px-2 py-0.5 rounded-full text-xs font-medium"
                  :class="t.kind === 'strength' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
                >{{ t.label }}</span>
                <span v-if="!p.profile.tags.length && p.profile.sample !== 'insuficiente'" class="text-xs text-slate-500">
                  sin un rasgo que destaque frente al circuito
                </span>
              </div>
              <dl class="grid grid-cols-2 sm:grid-cols-5 gap-x-4 gap-y-2 text-sm">
                <div v-for="m in profileMetrics(p.profile)" :key="m.label">
                  <dt class="text-xs text-slate-500">{{ m.label }}</dt>
                  <dd class="font-semibold text-slate-900">{{ m.value }}</dd>
                  <dd v-if="m.rank" class="text-xs text-slate-500">{{ m.rank }}</dd>
                </div>
              </dl>
              <p class="text-xs mt-2" :class="p.profile.sample === 'ok' ? 'text-slate-500' : 'text-amber-700'">
                Sobre {{ p.profile.matches }} partidos con estadísticas desde {{ p.profile.from }}.
                <span v-if="p.profile.sample === 'insuficiente'">Muy pocos para etiquetar o comparar con el circuito.</span>
                <span v-else-if="p.profile.sample === 'corta'">Muestra corta: tómalo como orientación.</span>
              </p>
            </div>
            <p v-else class="text-xs text-slate-500 mt-3">
              Sin estadísticas de saque y resto para este jugador (solo existen desde finales de julio de 2026).
            </p>
          </div>
        </div>
        <p v-if="!careerLoading && !surfaceCareerPlayers.length" class="text-sm text-slate-500">
          Ningún jugador de la base coincide con ese nombre. Prueba solo con el apellido.
        </p>
      </div>

      <!-- Global table (no search) -->
      <div v-if="!reliabilitySearch.trim()" class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-4">
        <h3 class="font-semibold text-slate-900 mb-3">Global — todos los jugadores</h3>
        <div v-for="(blk, surf) in reliabilityOverall" :key="surf" class="mb-4 last:mb-0">
          <div class="text-sm font-medium text-slate-700 mb-1">{{ surfaceLabel(surf) }}</div>
          <div class="overflow-x-auto" tabindex="0">
            <table class="min-w-full text-sm">
              <tbody>
                <tr v-for="r in blk.markets" :key="r.market" class="border-t border-slate-100">
                  <td class="py-1.5 pr-4 text-slate-700">{{ r.label }}</td>
                  <td class="py-1.5 px-3 font-semibold" :class="rateClass(r, blk)">{{ r.hitRate }}%</td>
                  <td class="py-1.5 px-2 text-xs text-slate-500">n={{ r.n }}</td>
                  <td class="py-1.5 px-2 text-xs">
                    <span v-if="blk.best && r.market === blk.best.market" class="text-green-700 font-medium">✓ mejor</span>
                    <span v-else-if="blk.worst && r.market === blk.worst.market" class="text-red-700 font-medium">✗ peor</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Player cards -->
      <div class="space-y-3">
        <div
          v-for="p in filteredReliabilityPlayers"
          :key="p.player"
          class="bg-white rounded-lg shadow-sm border border-slate-200 p-4"
        >
          <h3 class="font-semibold text-slate-900 mb-2">🎾 {{ p.player }}</h3>
          <div v-for="(blk, surf) in p.surfaces" :key="surf" class="mb-3 last:mb-0">
            <div class="text-sm font-medium text-slate-700 mb-1">
              {{ surfaceLabel(surf) }}
              <span class="text-xs font-normal text-slate-500">({{ blk.sampleTotal }} preds)</span>
            </div>
            <div v-if="blk.best || blk.worst" class="flex flex-wrap gap-2 mb-1 text-xs">
              <span v-if="blk.best" class="px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
                ✓ {{ blk.best.label }} — {{ blk.best.hitRate }}% (n={{ blk.best.n }})
              </span>
              <span v-if="blk.worst && (!blk.best || blk.worst.market !== blk.best.market)"
                    class="px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">
                ✗ {{ blk.worst.label }} — {{ blk.worst.hitRate }}% (n={{ blk.worst.n }})
              </span>
            </div>
            <div v-else class="text-xs text-slate-500 mb-1">Muestra insuficiente para destacar mejor/peor.</div>
            <div class="overflow-x-auto" tabindex="0">
              <table class="min-w-full text-sm">
                <tbody>
                  <tr v-for="r in blk.markets" :key="r.market" class="border-t border-slate-100">
                    <td class="py-1 pr-4 text-slate-600">{{ r.label }}</td>
                    <td class="py-1 px-3 font-medium">{{ r.hitRate }}%</td>
                    <td class="py-1 px-2 text-xs text-slate-500">n={{ r.n }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <EmptyState
          v-if="reliabilitySearch.trim() && !filteredReliabilityPlayers.length"
          icon="🔍"
          title="Sin datos para ese jugador"
          message="No hay predicciones validadas para un jugador con ese nombre todavía."
        />
      </div>

      <!-- Average points per set (1st..5th), optionally by surface -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mt-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-1">
          <h3 class="font-semibold text-slate-900">Puntos promedio por set</h3>
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2 flex-shrink-0">
            Superficie:
            <select
              v-model="pointsSurface"
              aria-label="Superficie para puntos por set"
              class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">Todas</option>
              <option value="clay">🟠 Arcilla</option>
              <option value="hard">🔵 Dura</option>
              <option value="grass">🟢 Hierba</option>
            </select>
          </label>
        </div>
        <p class="text-xs text-slate-500 mb-3">
          Puntos ganados-perdidos por set (1º a 5º) sobre los partidos FINISHED con detalle punto a punto{{ pointsSurface !== 'all' ? ` en ${surfaceLabel(pointsSurface)}` : '' }}.
          {{ reliabilitySearch.trim() ? 'Filtrado por el buscador de arriba.' : `Top ${pointsPerSetRows.length} por muestra; usa el buscador para uno concreto.` }}
        </p>
        <div class="overflow-x-auto" tabindex="0">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-4">Jugador</th>
                <th class="py-2 px-3">1er set</th>
                <th class="py-2 px-3">2º set</th>
                <th class="py-2 px-3">3er set</th>
                <th class="py-2 px-3">4º set</th>
                <th class="py-2 px-3">5º set</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in pointsPerSetRows" :key="p.player" class="border-t border-slate-100">
                <td class="py-2 pr-4 font-medium text-slate-900 whitespace-nowrap">{{ p.player }}</td>
                <td v-for="s in ['1','2','3','4','5']" :key="s" class="py-2 px-3 whitespace-nowrap">
                  <template v-if="p.sets[s]">
                    {{ p.sets[s].avgWon }}-{{ p.sets[s].avgLost }}
                    <span class="text-xs text-slate-500">(n={{ p.sets[s].n }})</span>
                  </template>
                  <span v-else class="text-xs text-slate-400">–</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState
          v-if="!pointsPerSetRows.length"
          icon="📈"
          title="Sin datos de puntos por set"
          :message="reliabilitySearch.trim() ? 'Ese jugador no tiene partidos con detalle punto a punto.' : 'Aún no hay partidos con detalle punto a punto.'"
        />
      </div>

      <!-- Last 3 matches per surface -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mt-4">
        <h3 class="font-semibold text-slate-900 mb-1">Últimos 3 partidos por superficie</h3>
        <p class="text-xs text-slate-500 mb-3">
          Partidos FINISHED más recientes de cada jugador en cada superficie (de la base, sin llamadas externas).
          {{ reliabilitySearch.trim() ? 'Filtrado por el buscador de arriba.' : 'Usa el buscador para un jugador concreto.' }}
        </p>
        <div class="space-y-3">
          <div v-for="p in recentBySurfaceRows" :key="p.player" class="border-t border-slate-100 pt-3 first:border-0 first:pt-0">
            <div class="font-medium text-slate-900 mb-1">🎾 {{ p.player }}</div>
            <div v-for="surf in ['clay', 'hard', 'grass']" :key="surf" v-show="p.surfaces[surf]" class="mb-2 last:mb-0">
              <div class="text-xs font-medium text-slate-600 mb-0.5">{{ surfaceLabel(surf) }}</div>
              <ul class="text-sm text-slate-700 space-y-0.5">
                <li v-for="(mt, i) in (p.surfaces[surf] || [])" :key="i" class="flex flex-wrap items-baseline gap-x-2">
                  <span class="font-semibold" :class="mt.result === 'W' ? 'text-green-700' : mt.result === 'L' ? 'text-red-600' : 'text-slate-500'">
                    {{ mt.result || '·' }} {{ mt.score || '' }}
                  </span>
                  <span>vs {{ mt.opponent || '?' }}</span>
                  <span class="text-xs text-slate-500">{{ mt.date }}<span v-if="mt.tournament"> · {{ mt.tournament }}</span></span>
                </li>
              </ul>
            </div>
          </div>
        </div>
        <EmptyState
          v-if="!recentBySurfaceRows.length"
          icon="🎾"
          title="Sin partidos"
          :message="reliabilitySearch.trim() ? 'Ese jugador no tiene partidos terminados en la base.' : 'Escribe un nombre en el buscador.'"
        />
      </div>
    </div>

    <!-- Bets view: highest-confidence picks across today's tennis matches -->
    <div v-else-if="activeTab === 'bets'">
      <!-- Best bets still to play: every match, both sides, by price value -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <h2 class="text-lg font-semibold text-slate-900">💰 Mejores apuestas por jugar</h2>
          <div class="inline-flex rounded-md border border-slate-300 overflow-hidden text-sm" role="group" aria-label="Orden de la lista">
            <button
              type="button"
              class="px-3 py-1.5"
              :class="bestBetsMode === 'value' ? 'bg-blue-600 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'"
              :aria-pressed="bestBetsMode === 'value'"
              @click="bestBetsMode = 'value'"
            >Por valor</button>
            <button
              type="button"
              class="px-3 py-1.5 border-l border-slate-300"
              :class="bestBetsMode === 'safe' ? 'bg-blue-600 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'"
              :aria-pressed="bestBetsMode === 'safe'"
              @click="bestBetsMode = 'safe'"
            >Más seguras</button>
          </div>
        </div>
        <p v-if="bestBetsMode === 'value'" class="text-sm text-slate-500 mb-3">
          Los dos lados de cada partido, en ganador del partido y primer set, ordenados por edge a la mejor cuota
          entre las casas. "Justa" es la probabilidad de la casa de referencia sin su margen; el motor y el modelo de
          saque y resto van al lado como segundas opiniones.
        </p>
        <p v-else class="text-sm text-slate-500 mb-3">
          Los favoritos, de más a menos probable: las apuestas donde se puede poner más dinero porque es menos
          probable perderlo. "Histórico" es cómo les fue a favoritos del mismo tramo de probabilidad en el último año
          a la cuota de referencia (cuántos ganaron contra lo que se esperaba, y lo que dejó apostar plano).
        </p>
        <p v-if="!bestBetsList.length" class="text-sm text-slate-500">No hay partidos por jugar con cuota.</p>
        <div v-else-if="bestBetsMode === 'safe'" class="overflow-x-auto" tabindex="0" role="region" aria-label="Apuestas más seguras por jugar">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-3">Apuesta</th>
                <th class="py-2 px-3">Cuándo</th>
                <th class="py-2 px-3">Mejor cuota</th>
                <th class="py-2 px-3">Gana</th>
                <th class="py-2 px-3">Con $100</th>
                <th class="py-2 px-3">Histórico del tramo</th>
                <th class="py-2 px-3">Motor</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in bestBetsShown" :key="'s' + b.matchId + b.market + b.pick" class="border-t border-slate-100">
                <td class="py-2 pr-3">
                  <span class="font-medium text-slate-900">{{ MARKET_ES[b.market] || b.market }} — {{ b.pick }}</span>
                  <span class="block text-xs text-slate-500">{{ b.home }} vs {{ b.away }}<template v-if="b.tournament"> · {{ b.tournament }}</template></span>
                </td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">{{ betWhen(b) }}</td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="font-semibold text-slate-900">{{ b.bestOdds.toFixed(2) }}</span>
                  <span class="ml-1 text-xs text-slate-600">{{ b.bestBook || '' }}</span>
                  <span v-if="b.level === 'check'" class="block text-xs text-amber-800">🔎 confirma la cuota</span>
                </td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="font-semibold text-slate-900">{{ pct(b.fairProbability) }}%</span>
                  <span class="block text-xs text-slate-500">pierde {{ 100 - pct(b.fairProbability) }}%</span>
                </td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="text-green-700 font-semibold">+${{ Math.round((b.bestOdds - 1) * 100) }}</span>
                  <span class="block text-xs text-slate-500">o −$100</span>
                </td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <template v-if="b.bandHistory">
                    <span class="text-slate-700">ganó {{ pct(b.bandHistory.winRate) }}% <span class="text-xs text-slate-500">(se esperaba {{ pct(b.bandHistory.expected) }}%)</span></span>
                    <span class="block text-xs">
                      <span :class="yieldClass(b.bandHistory.yield)" class="font-medium">{{ formatEdge(b.bandHistory.yield) }}</span>
                      <span class="text-slate-500"> por apuesta · {{ b.bandHistory.n }} apuestas</span>
                    </span>
                  </template>
                  <span v-else class="text-slate-500">–</span>
                </td>
                <td class="py-2 px-3 text-slate-600">{{ b.engineProbability != null ? pct(b.engineProbability) + '%' : '–' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="overflow-x-auto" tabindex="0" role="region" aria-label="Mejores apuestas por jugar">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-3">Apuesta</th>
                <th class="py-2 px-3">Cuándo</th>
                <th class="py-2 px-3">Mejor cuota</th>
                <th class="py-2 px-3">Justa</th>
                <th class="py-2 px-3">Edge</th>
                <th class="py-2 px-3">Motor</th>
                <th class="py-2 px-3">Saque/resto</th>
                <th class="py-2 px-3">¼ Kelly</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in bestBetsShown" :key="b.matchId + b.market + b.pick" class="border-t border-slate-100">
                <td class="py-2 pr-3">
                  <span class="font-medium text-slate-900">{{ MARKET_ES[b.market] || b.market }} — {{ b.pick }}</span>
                  <span class="block text-xs text-slate-500">{{ b.home }} vs {{ b.away }}<template v-if="b.tournament"> · {{ b.tournament }}</template></span>
                </td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">{{ betWhen(b) }}</td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="font-semibold text-slate-900">{{ b.bestOdds.toFixed(2) }}</span>
                  <span class="ml-1 text-xs text-slate-600">{{ b.bestBook || '' }}</span>
                  <span v-if="b.bestOdds > b.referenceOdds" class="block text-xs text-slate-500">ref. {{ b.referenceOdds.toFixed(2) }}</span>
                </td>
                <td class="py-2 px-3 text-slate-600">{{ pct(b.fairProbability) }}%</td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="font-semibold" :class="b.edge >= 0 ? 'text-green-700' : 'text-red-700'">{{ formatEdge(b.edge) }}</span>
                  <span class="block mt-0.5"><span class="inline-block rounded-full px-2 py-0.5 text-xs font-medium" :class="BEST_BET_BADGE[b.level].cls">{{ BEST_BET_BADGE[b.level].text }}</span></span>
                </td>
                <td class="py-2 px-3 text-slate-600">{{ b.engineProbability != null ? pct(b.engineProbability) + '%' : '–' }}</td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  {{ b.pointProbability != null ? pct(b.pointProbability) + '%' : '–' }}
                  <span v-if="b.pointProbability != null && b.pointTrust < 0.5" class="text-xs text-slate-500" title="Poca historia de saque y resto de alguno de los dos">*</span>
                </td>
                <td class="py-2 px-3 text-slate-600">{{ b.kelly > 0 ? (b.kelly * 25).toFixed(1) + '%' : '0%' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <button
          v-if="bestBetsList.length > 8"
          type="button"
          class="mt-3 text-sm font-medium text-blue-600 hover:text-blue-700"
          @click="showAllBestBets = !showAllBestBets"
        >{{ showAllBestBets ? 'Ver menos' : `Ver las ${bestBetsList.length}` }}</button>
        <details v-if="bestBetsMode === 'safe' && bandHistoryRows.length" class="mt-3 text-sm">
          <summary class="cursor-pointer text-slate-700 font-medium">Cómo les fue a los favoritos, por tramo (último año)</summary>
          <div class="overflow-x-auto mt-2" tabindex="0" role="region" aria-label="Histórico de favoritos por tramo">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-1 pr-3">Mercado</th>
                  <th class="py-1 px-3">Prob. justa</th>
                  <th class="py-1 px-3">Apuestas</th>
                  <th class="py-1 px-3">Ganaron</th>
                  <th class="py-1 px-3">Esperado</th>
                  <th class="py-1 px-3">Por apuesta</th>
                  <th class="py-1 px-3">Rango 95%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in bandHistoryRows" :key="r.market + r.band" class="border-t border-slate-100">
                  <td class="py-1 pr-3 text-slate-700">{{ MARKET_ES[r.market] || r.market }}</td>
                  <td class="py-1 px-3 text-slate-700">{{ r.band }}%</td>
                  <td class="py-1 px-3 text-slate-600">{{ r.n }}</td>
                  <td class="py-1 px-3 text-slate-700">{{ pct(r.winRate) }}%</td>
                  <td class="py-1 px-3 text-slate-600">{{ pct(r.expected) }}%</td>
                  <td class="py-1 px-3 font-medium" :class="yieldClass(r.yield)">{{ formatEdge(r.yield) }}</td>
                  <td class="py-1 px-3 text-slate-600 whitespace-nowrap">{{ formatEdge(r.yieldLow) }} a {{ formatEdge(r.yieldHigh) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
        <p v-if="bestBetsMode === 'safe'" class="text-xs text-slate-500 mt-3">
          Más segura no es lo mismo que rentable: un favorito a 1.10 gana casi siempre, pero una sola derrota se come
          diez victorias. Si el rango del histórico cruza el cero, ese tramo no ha demostrado dejar ganancia.
        </p>
        <p v-else class="text-xs text-slate-500 mt-3">
          Verde: edge de 2% o más. "Confirma la cuota": el precio supera en más de 6% al de referencia, y en el
          histórico eso casi siempre fue una cuota vieja. Ninguno de los dos modelos ha demostrado ganarle a la casa:
          son información, no garantía.
        </p>
      </div>

      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-slate-900">🎯 Recomendaciones de hoy — Tenis</h2>
            <p class="text-sm text-slate-500">
              Qué apostar sin entrar al detalle. Máx. 3 picks por partido.
            </p>
          </div>
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2 flex-shrink-0">
            Filtro:
            <select
              v-model.number="minEdge"
              aria-label="Filtro de recomendaciones"
              class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option :value="0.1">Alto valor: edge &gt; 10%</option>
              <option :value="0.05">Valor: edge &gt; 5%</option>
              <option :value="0">Con cuota: edge ≥ 0%</option>
              <option :value="-1">Todas (por confianza)</option>
            </select>
          </label>
        </div>
        <label
          v-if="minEdge < 0"
          class="text-xs font-medium text-slate-600 flex items-center gap-2 mt-3"
        >
          Confianza mínima:
          <select
            v-model.number="minConfidence"
            aria-label="Confianza mínima"
            class="px-2 py-1 border border-slate-300 rounded text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option :value="45">45%</option>
            <option :value="50">50%</option>
            <option :value="55">55%</option>
            <option :value="60">60%</option>
            <option :value="65">65%</option>
          </select>
        </label>
        <p class="text-xs text-slate-500 mt-3">
          <template v-if="minEdge >= 0">
            <b>{{ bettingRecs.length }}</b> partido(s) con valor real ·
            <b>{{ bettingPickCount }}</b> apuesta(s) con edge en Match Winner, Total Sets, Set 1 Winner y
            Marcador exacto (según cuotas disponibles). Los picks sin edge suficiente van debajo como
            <span class="text-slate-500">contexto</span>. Orden: mayor edge primero.
          </template>
          <template v-else>
            {{ bettingRecs.length }} partido(s) sobre {{ minConfidence }}% de confianza
            <b>calibrada</b> (los modelos de tenis se calibran a la baja; tope ~65%).
            <b>{{ bettingPickCount }}</b> pick(s), orden: edge y luego confianza.
          </template>
        </p>
      </div>

      <div class="space-y-3">
        <div
          v-for="rec in bettingRecs"
          :key="rec.matchId"
          class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden"
        >
          <div class="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-3">
            <span class="font-semibold text-slate-900 truncate">🎾 {{ rec.home }} <span class="text-slate-500 font-normal">vs</span> {{ rec.away }}</span>
            <span class="text-xs text-slate-500 flex-shrink-0">
              <span v-if="rec.tournament">{{ rec.tournament }}</span>
              <span v-if="rec.time && rec.time !== '00:00'"> · {{ rec.time }}</span>
            </span>
          </div>
          <ul class="divide-y divide-slate-100">
            <li
              v-for="pick in rec.picks"
              :key="pick.id"
              class="px-4 py-2.5 flex items-center justify-between gap-3"
              :class="pick.context ? 'bg-slate-50/60' : ''"
            >
              <div class="min-w-0">
                <span class="inline-block text-xs font-medium rounded px-1.5 py-0.5 mr-2 text-slate-600 bg-slate-100">{{ pick.market }}</span>
                <span class="font-semibold" :class="pick.context ? 'text-slate-600' : 'text-slate-900'">{{ pick.prediction }}</span>
                <span v-if="pick.context" class="ml-2 text-[10px] uppercase tracking-wide text-slate-500">contexto</span>
              </div>
              <div class="flex items-center gap-2 flex-shrink-0">
                <span
                  v-if="pick.edge != null"
                  :class="edgeLabel(pick.edge).cls"
                  class="text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
                  :title="`Edge frente a la cuota: ${formatEdge(pick.edge)}`
                    + (pick.modelEdge != null ? ` · modelo solo: ${formatEdge(pick.modelEdge)}${isSuspicious(pick.modelEdge) ? ' (dudoso: más de 20%)' : ''}` : '')
                    + (pick.kelly ? ` · ¼ Kelly: ${(pick.kelly * 25).toFixed(1)}% de la caja` : '')"
                >
                  {{ edgeLabel(pick.edge).text }}
                </span>
                <span v-else class="text-xs text-slate-500 whitespace-nowrap">sin cuota</span>
                <span
                  class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold whitespace-nowrap"
                  :class="pick.confidence >= 75 ? 'bg-blue-600 text-white' : 'bg-blue-100 text-blue-700'"
                >
                  {{ Math.round(pick.confidence) }}%
                </span>
              </div>
            </li>
          </ul>
        </div>
      </div>

      <EmptyState
        v-if="!bettingRecs.length"
        icon="🎯"
        :title="minEdge >= 0 ? 'Sin apuestas con valor hoy' : 'Sin recomendaciones'"
        :message="minEdge >= 0
          ? 'Ningún pick de hoy tiene esa ventaja frente a la cuota de la casa. Es lo normal: hoy el histórico solo justifica darle al modelo un peso pequeño frente al mercado. Puedes bajar el filtro para ver los que más se acercan.'
          : `Ningún pick de hoy supera el ${minConfidence}% de confianza.`"
      />

      <!-- Parlays / combinadas -->
      <div v-if="minEdge >= 0" class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden mt-4">
        <div class="px-4 py-3 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h2 class="text-lg font-semibold text-slate-900">🧩 Combinadas recomendadas</h2>
            <p class="text-xs text-slate-500">
              1 leg por partido · solo legs donde el modelo va con el mercado
              (|p−cuota| &lt; {{ comboLegs >= 3 ? '10' : '15' }}pts, más estricto a 3 legs) ·
              EV combinado &gt; 0. Los EV son del modelo (sobre-confiados; se muestran capados al 100%).
            </p>
          </div>
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2 flex-shrink-0">
            Legs:
            <select
              v-model.number="comboLegs"
              aria-label="Legs por combinada"
              class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option :value="2">2</option>
              <option :value="3">3</option>
            </select>
          </label>
        </div>
        <ul class="divide-y divide-slate-100">
          <li v-for="(c, i) in combos" :key="i" class="px-4 py-3">
            <div class="space-y-1 mb-2">
              <div
                v-for="l in c.legs"
                :key="l.matchId + l.market"
                class="text-sm flex items-center justify-between gap-2"
              >
                <span class="min-w-0 truncate">
                  <span class="text-slate-500">{{ l.home }} vs {{ l.away }} — </span>
                  <span class="font-medium text-slate-700">{{ l.market }}:</span>
                  {{ l.prediction }}
                </span>
                <span class="text-xs text-slate-500 flex-shrink-0 whitespace-nowrap">
                  @{{ l.odd.toFixed(2) }} · {{ Math.round(l.prob * 100) }}%
                </span>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">cuota {{ c.oddsCombo.toFixed(2) }}</span>
              <span class="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-semibold">prob {{ (c.pCombo * 100).toFixed(0) }}%</span>
              <span
                class="px-2 py-0.5 rounded-full font-semibold"
                :class="c.evShown > 0.10 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'"
                :title="c.evCapped ? `EV del modelo ${(c.evCombo * 100).toFixed(0)}% — capado en pantalla` : ''"
              >EV +{{ (c.evShown * 100).toFixed(0) }}%{{ c.evCapped ? '+' : '' }}</span>
              <span class="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">stake ¼ Kelly {{ (c.kelly * 25).toFixed(1) }}%</span>
            </div>
          </li>
        </ul>
        <p v-if="!combos.length" class="px-4 py-6 text-sm text-slate-500 text-center">
          No hay combinadas con EV positivo hoy — pocas legs pasan el filtro modelo↔mercado.
        </p>
      </div>
    </div>

    <!-- Today view: sport split, or grouped by tournament via the toggle -->
    <div v-else>
      <div class="flex justify-end mb-4">
        <div class="inline-flex rounded-lg border border-slate-300 overflow-hidden text-sm">
          <button
            @click="groupByTournament = false"
            :class="groupByTournament ? 'bg-white text-slate-600' : 'bg-blue-600 text-white'"
            class="px-3 py-1.5 font-medium"
          >
            Por deporte
          </button>
          <button
            @click="groupByTournament = true"
            :class="groupByTournament ? 'bg-blue-600 text-white' : 'bg-white text-slate-600'"
            class="px-3 py-1.5 font-medium border-l border-slate-300"
          >
            Por torneo
          </button>
        </div>
      </div>

      <!-- Grouped by tournament / league -->
      <div v-if="groupByTournament" class="space-y-4">
        <details
          v-for="group in tournamentGroups"
          :key="group.name"
          open
          class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden"
        >
          <summary class="cursor-pointer select-none px-4 py-3 flex items-center justify-between gap-3 hover:bg-slate-50">
            <span class="flex items-center gap-2 font-semibold text-slate-900 min-w-0">
              <span class="flex-shrink-0">{{ group.icon }}</span>
              <span class="truncate">{{ group.name }}</span>
              <span class="text-sm font-normal text-slate-500 flex-shrink-0">({{ group.matches.length }})</span>
            </span>
          </summary>
          <div class="px-4 pb-4 pt-1 space-y-3 border-t border-slate-100">
            <MatchCard
              v-for="match in group.matches"
              :key="match.matchId"
              :match="match"
              :sport="match._sport"
              :best-confidence="bestConfidenceByMatch[match.matchId] ?? null"
              :is-top="top3MatchIds.has(match.matchId)"
              :reliability="match._sport === 'tennis' ? matchReliability(match) : null"
            />
          </div>
        </details>
        <EmptyState
          v-if="!tournamentGroups.length"
          icon="🏆"
          title="No hay torneos"
          message="No hay partidos disponibles para hoy."
        />
      </div>

      <!-- Sport split -->
      <div v-else class="grid grid-cols-1 gap-8" :class="footballMatches.length ? 'lg:grid-cols-2' : ''">
        <div>
          <h2 class="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <span>🎾</span> Tenis
            <span class="text-sm font-normal text-slate-500">({{ tennisMatches.length }})</span>
          </h2>
          <!-- Without football the tennis cards use both columns -->
          <div :class="footballMatches.length ? 'space-y-4' : 'grid grid-cols-1 lg:grid-cols-2 gap-4 items-start'">
            <MatchCard
              v-for="match in tennisMatches"
              :key="match.matchId"
              :match="match"
              sport="tennis"
              :best-confidence="bestConfidenceByMatch[match.matchId] ?? null"
              :is-top="top3MatchIds.has(match.matchId)"
              :reliability="matchReliability(match)"
            />
            <EmptyState
              v-if="!tennisMatches.length"
              icon="🎾"
              title="No hay partidos de tenis"
              message="No hay partidos disponibles para hoy."
            />
          </div>
        </div>

        <div v-if="footballMatches.length">
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
          </div>
        </div>
      </div>
    </div>

    <!-- Player set stats (tennis, today) -->
    <div v-if="activeTab === 'today' && setStatsPlayers.length" class="mt-8 bg-white rounded-lg shadow-sm border border-slate-200 p-4">
      <h2 class="text-lg font-semibold text-slate-900 mb-1">🎾 Games y puntos por set — jugadores de hoy</h2>
      <p class="text-sm text-slate-500 mb-4">
        Promedio de games y puntos ganados-perdidos por set en cada superficie, sobre los partidos con detalle por set.
      </p>
      <div class="overflow-x-auto" tabindex="0">
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
                  <span class="text-xs text-slate-600">({{ p.surfaces[surf].setsPlayed }})</span>
                  <div v-if="p.surfaces[surf].avgPointsWon != null" class="text-xs text-slate-600">
                    {{ p.surfaces[surf].avgPointsWon }}-{{ p.surfaces[surf].avgPointsLost }} pts
                  </div>
                </span>
                <span v-else class="text-xs text-slate-600">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-xs text-slate-500 mt-2">
        Formato: games ganados-perdidos por set (sets con datos) y, debajo, puntos por set cuando hay estadísticas.
        Resaltado = superficie del partido de hoy.
      </p>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useMatchesStore } from '../stores/matches.js'
import { usePredictionsStore } from '../stores/predictions.js'
import { useAnalyticsStore } from '../stores/analytics.js'
import MatchCard from '../components/MatchCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { betEdge, betKelly, betProbability, modelEdge, isSuspicious, formatEdge, edgeLabel } from '../utils/edge.js'
import { clearApiCache } from '../stores/api.js'

const matchesStore = useMatchesStore()
const predictionsStore = usePredictionsStore()
const analyticsStore = useAnalyticsStore()

const lastLoadedAt = ref(null)
const refreshing = ref(false)
const dash = computed(() => analyticsStore.dashboard)

function fmtClock(d) {
  return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Bogota' })
}
function ago(iso) {
  if (!iso) return '—'
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (mins < 1) return 'ahora'
  if (mins < 60) return `hace ${mins} min`
  const h = Math.floor(mins / 60)
  if (h < 24) return `hace ${h} h`
  return `hace ${Math.floor(h / 24)} d`
}
async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  clearApiCache()
  try {
    await Promise.all([loadToday(), analyticsStore.fetchDashboard()])
    lastLoadedAt.value = new Date()
  } finally {
    refreshing.value = false
  }
}

const tabs = [
  { id: 'today', label: 'Hoy' },
  { id: 'bets', label: 'Apuestas' },
  { id: 'reliability', label: 'Fiabilidad' },
]
const activeTab = ref('today')
const groupByTournament = ref(false)

function getUtcTodayStr() {
  // Use America/Bogota timezone (UTC-5) so "today" matches the user's local date
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
}

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

// All matches (both sports) grouped by tournament / league name
const tournamentGroups = computed(() => {
  const groups = {}
  const addMatch = (match, sport) => {
    const name = match.tournament || match.league || 'Sin torneo'
    if (!groups[name]) groups[name] = { name, sports: new Set(), matches: [] }
    groups[name].sports.add(sport)
    groups[name].matches.push({ ...match, _sport: sport })
  }
  for (const m of matchesStore.latest?.tennis || []) addMatch(m, 'tennis')
  for (const m of matchesStore.latest?.football || []) addMatch(m, 'football')
  return Object.values(groups)
    .map((g) => ({
      name: g.name,
      matches: sortByConfidence(g.matches),
      icon: g.sports.has('tennis') && g.sports.has('football')
        ? '🎾⚽'
        : g.sports.has('tennis') ? '🎾' : '⚽'
    }))
    .sort((a, b) => b.matches.length - a.matches.length || a.name.localeCompare(b.name))
})
const setStatsPlayers = computed(() => matchesStore.playerSetStats?.players || [])

// --- Betting recommendations (tab "Apuestas") ---
// minEdge: -1 = "todas" (filter by confidence instead); >= 0 = only picks with
// a real edge above that threshold (edge only exists for Match Winner).
const minEdge = ref(0.05)
const minConfidence = ref(50)

// Markets excluded from every betting-recommendation surface (picks,
// parlays, "apuesta del día") while under review/redesign. "Exact Set
// Score" showed a statistically significant loss that got WORSE in the
// second half of its history (see Caja's "¿El edge se sostiene en el
// tiempo?"), so it's paused here on 2026-10-02 pending a redesign of how
// the engine prices 6-way exact-score markets. Predictions keep being
// generated and validated for it (still visible on PredictionDetail) --
// this only stops it from being recommended as something to stake on.
// Mirrored on the backend as bankroll_service.PAUSED_BETTING_MARKETS --
// update both sides together.
const PAUSED_BETTING_MARKETS = new Set(['Exact Set Score'])

const tennisMatchById = computed(() => {
  const map = {}
  for (const m of matchesStore.latest?.tennis || []) map[m.matchId] = m
  return map
})

// Best edge first (nulls last), then confidence.
function pickByValue(a, b) {
  const ea = a.edge ?? -Infinity
  const eb = b.edge ?? -Infinity
  if (ea !== eb) return eb - ea
  return (b.confidence ?? 0) - (a.confidence ?? 0)
}

const bettingRecs = computed(() => {
  const today = getUtcTodayStr()
  const edgeMode = minEdge.value >= 0
  const byMatch = {}
  // Collect EVERY tennis pick for today, per match.
  for (const p of predictionsStore.latest?.predictions || []) {
    if (String(p.sport).toLowerCase() !== 'tennis') continue
    if (PAUSED_BETTING_MARKETS.has(p.market)) continue
    if (p.eventDate && p.eventDate !== today) continue
    // No price, no bet: markets without odds (Total Aces) stay in Predicciones.
    if (betEdge(p) == null) continue
    const conf = p.calibratedConfidence ?? p.confidence
    const m = tennisMatchById.value[p.matchId] || {}
    if (!byMatch[p.matchId]) {
      byMatch[p.matchId] = {
        matchId: p.matchId,
        home: p.homeName || m.player1 || 'Jugador 1',
        away: p.awayName || m.player2 || 'Jugador 2',
        time: m.eventTime || p.eventTime || null,
        tournament: m.tournament || null,
        picks: []
      }
    }
    byMatch[p.matchId].picks.push({
      id: p.predictionId || p.id,
      market: p.market,
      prediction: p.prediction,
      confidence: conf,
      // Anchored to the bookmaker's price; the model's own edge rides along
      // so an implausible one can be flagged next to it.
      edge: betEdge(p),
      modelEdge: modelEdge(p),
      kelly: betKelly(p)
    })
  }

  const out = []
  for (const rec of Object.values(byMatch)) {
    let picks
    if (edgeMode) {
      const value = rec.picks
        .filter((pk) => pk.edge != null && pk.edge > minEdge.value)
        .sort(pickByValue)
      if (!value.length) continue // no real betting value in this match
      // Show the value pick(s), then fill up to 3 with the rest as context.
      const rest = rec.picks
        .filter((pk) => !value.includes(pk))
        .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
        .map((pk) => ({ ...pk, context: true }))
      picks = [...value, ...rest].slice(0, 3)
    } else {
      picks = rec.picks
        .filter((pk) => pk.confidence != null && pk.confidence >= minConfidence.value)
        .sort(pickByValue)
        .slice(0, 3)
      if (!picks.length) continue
    }
    out.push({ ...rec, picks })
  }
  return out.sort((a, b) => pickByValue(a.picks[0], b.picks[0]))
})

const bettingPickCount = computed(() =>
  bettingRecs.value.reduce((n, r) => n + r.picks.filter((p) => !p.context).length, 0)
)

// --- Parlays / combinadas ---
const comboLegs = ref(2)

function comboLegOdd(p) {
  const od = p.reasoningData?.oddsDecimal
  if (!od) return null
  if (od.chosen != null) return Number(od.chosen)
  if (od.player1 != null && od.player2 != null) {
    return Number(p.prediction === p.homeName ? od.player1 : od.player2)
  }
  return null
}
function comboLegProb(p) {
  // Market-anchored probability when the pick has odds; otherwise the
  // model's (calibrated, raw for Exact Set Score) -- see utils/edge.js.
  return betProbability(p)
}

// Model overconfidence compounds in a parlay, so the tolerance for the
// model disagreeing with the market tightens as legs are added.
const COMBO_MAX_DIVERGENCE = { 2: 0.15, 3: 0.10 }
const COMBO_MIN_LEG_PROB = { 2: 0.35, 3: 0.42 }
// Displayed EV is capped; a combined EV above this is model noise, not signal.
const COMBO_EV_DISPLAY_CAP = 1.0
const COMBO_EV_DROP = 2.5

// Best qualifying leg per match: has odds, model agrees with the market
// (kills the +50% artifacts), not a longshot, positive edge. The thresholds
// depend on how many legs the combo will have.
const comboPool = computed(() => {
  const today = getUtcTodayStr()
  const k = comboLegs.value
  const maxDiv = COMBO_MAX_DIVERGENCE[k] ?? 0.15
  const minProb = COMBO_MIN_LEG_PROB[k] ?? 0.35
  const byMatch = {}
  for (const p of predictionsStore.latest?.predictions || []) {
    if (String(p.sport).toLowerCase() !== 'tennis') continue
    if (PAUSED_BETTING_MARKETS.has(p.market)) continue
    if (p.eventDate && p.eventDate !== today) continue
    const odd = comboLegOdd(p)
    const prob = comboLegProb(p)
    if (odd == null || odd <= 1 || prob == null) continue
    if (prob < minProb) continue
    if (Math.abs(prob - 1 / odd) > maxDiv) continue
    const ev = prob * odd - 1
    if (ev <= 0) continue
    const m = tennisMatchById.value[p.matchId] || {}
    const leg = {
      matchId: p.matchId,
      home: p.homeName || m.player1 || 'J1',
      away: p.awayName || m.player2 || 'J2',
      market: p.market,
      prediction: p.prediction,
      odd, prob, ev
    }
    if (!byMatch[p.matchId] || leg.ev > byMatch[p.matchId].ev) byMatch[p.matchId] = leg
  }
  return Object.values(byMatch).sort((a, b) => b.ev - a.ev)
})

function combinationsOf(arr, k) {
  const res = []
  const rec = (start, acc) => {
    if (acc.length === k) { res.push(acc.slice()); return }
    for (let i = start; i < arr.length; i++) { acc.push(arr[i]); rec(i + 1, acc); acc.pop() }
  }
  rec(0, [])
  return res
}

const combos = computed(() => {
  const pool = comboPool.value
  const k = comboLegs.value
  if (pool.length < k) return []
  return combinationsOf(pool, k)
    .map((legs) => {
      const pCombo = legs.reduce((x, l) => x * l.prob, 1)
      const oddsCombo = legs.reduce((x, l) => x * l.odd, 1)
      const evCombo = pCombo * oddsCombo - 1
      const b = oddsCombo - 1
      const kelly = b > 0 ? Math.max(0, (b * pCombo - (1 - pCombo)) / b) : 0
      return {
        legs,
        pCombo,
        oddsCombo,
        evCombo,
        evShown: Math.min(evCombo, COMBO_EV_DISPLAY_CAP),
        evCapped: evCombo > COMBO_EV_DISPLAY_CAP,
        kelly: Math.min(kelly, 4 * COMBO_EV_DISPLAY_CAP) // keep ¼-Kelly stake sane too
      }
    })
    .filter((c) => c.evCombo > 0 && c.evCombo <= COMBO_EV_DROP)
    .sort((a, b) => b.evCombo - a.evCombo)
    .slice(0, 8)
})

// --- Pick of the day: the single most attention-worthy single bet ---
const MARKET_ES = {
  'Match Winner': 'Ganador',
  'Set 1 Winner': 'Ganador 1er set',
  'Total Sets': 'Total de sets',
  'Exact Set Score': 'Marcador exacto'
}
// The card always shows today's best bet among matches still to start, even
// when its edge is negative, and says so with its colour. The edge is taken
// at the BEST price across the bookmakers collected, against the fair
// probability (the reference bookmaker without its margin):
//   good  (green)  edge >= 2%      -> a price clearly above the fair one
//   fair  (yellow) 0% <= edge < 2% -> a slight one
//   poor  (red)    edge < 0%       -> the least bad of the day, not a recommendation
// A price more than 6% above the reference has historically been a stale or
// wrong quote (those bets lost), so it is shown yellow with a warning and
// ranked below the believable ones.
const POD_GOOD_EDGE = 0.02
const POD_STALE_GAP = 0.06
const POD_STYLE = {
  good: {
    card: 'from-blue-600 to-blue-700 text-white', sub: 'text-white/90', btn: 'bg-white/15 hover:bg-white/25',
    icon: '🏆', title: 'Apuesta del día · precio por encima del justo'
  },
  fair: {
    card: 'from-yellow-300 to-amber-400 text-slate-900', sub: 'text-slate-800', btn: 'bg-black/10 hover:bg-black/20',
    icon: '⚖️', title: 'Lo mejor de hoy · ventaja leve'
  },
  check: {
    card: 'from-yellow-300 to-amber-400 text-slate-900', sub: 'text-slate-800', btn: 'bg-black/10 hover:bg-black/20',
    icon: '🔎', title: 'Lo mejor de hoy · confirma la cuota antes de apostar'
  },
  poor: {
    card: 'from-red-700 to-red-800 text-white', sub: 'text-white/90', btn: 'bg-white/15 hover:bg-white/25',
    icon: '⚠️', title: 'La menos mala de hoy · sin ventaja'
  }
}
const pct = (x) => Math.round(x * 100)
const pickCandidates = computed(() => {
  const today = getUtcTodayStr()
  const nowHm = new Date().toLocaleTimeString('en-GB', { timeZone: 'America/Bogota', hour: '2-digit', minute: '2-digit' })
  const out = []
  for (const p of predictionsStore.latest?.predictions || []) {
    if (String(p.sport).toLowerCase() !== 'tennis') continue
    if (PAUSED_BETTING_MARKETS.has(p.market)) continue
    if (p.eventDate && p.eventDate !== today) continue
    const m = tennisMatchById.value[p.matchId] || {}
    if (m.status && m.status !== 'SCHEDULED') continue
    // The status lags the hourly score update: also trust the clock.
    const startsAt = m.eventTime || p.eventTime
    if (startsAt && startsAt !== '00:00' && startsAt <= nowHm) continue
    const refOdd = comboLegOdd(p)
    const prob = comboLegProb(p)
    if (refOdd == null || refOdd <= 1 || prob == null || betEdge(p) == null) continue
    const odd = p.bestOdds ?? refOdd
    const edge = p.bestEdge ?? betEdge(p)
    const stale = (p.bestPriceGap ?? 0) > POD_STALE_GAP
    const b = odd - 1
    const kelly = b > 0 ? Math.max(0, (b * prob - (1 - prob)) / b) : 0
    const level = edge < 0 ? 'poor' : stale ? 'check' : edge >= POD_GOOD_EDGE ? 'good' : 'fair'
    const house = p.marketProbability != null ? pct(p.marketProbability) : pct(1 / refOdd)

    const parts = []
    parts.push(p.bestBook
      ? `Mejor cuota: ${odd.toFixed(2)} en ${p.bestBook}` + (odd > refOdd ? ` (la de referencia paga ${refOdd.toFixed(2)}).` : '.')
      : `Cuota ${odd.toFixed(2)}.`)
    parts.push(`Probabilidad justa según la casa de referencia, sin su margen: ${house}% → edge ${formatEdge(edge)}.`)
    const opinions = [`motor ${pct(p.modelProbability ?? p.confidence / 100)}%`]
    if (p.pointProbability != null) {
      opinions.push(`modelo de saque y resto ${pct(p.pointProbability)}%` + (p.pointTrust < 0.5 ? ' (poca historia)' : ''))
    }
    parts.push(`Segundas opiniones: ${opinions.join(' · ')}.`)
    if (level === 'check') parts.push('Esa cuota está muy por encima de la referencia: en el histórico eso casi siempre fue un precio viejo. Confírmala en la casa.')
    if (level === 'poor') parts.push('Es el mejor edge de hoy, no una ventaja.')

    out.push({
      id: p.predictionId || p.id,
      level,
      stale,
      market: MARKET_ES[p.market] || p.market,
      prediction: p.prediction,
      home: p.homeName || m.player1 || 'J1',
      away: p.awayName || m.player2 || 'J2',
      tournament: m.tournament || null,
      time: m.eventTime || p.eventTime || null,
      link: `/predictions/${p.predictionId || p.id}`,
      odd, prob, edge, kelly,
      why: parts.join(' ')
    })
  }
  // Believable prices first, then best edge; among equals, the likelier pick.
  return out.sort((a, b) => (a.stale - b.stale) || (b.edge - a.edge) || (b.prob - a.prob))
})
// --- Best bets still to play: both sides of every match, ranked by the backend ---
const showAllBestBets = ref(false)
const bestBets = computed(() => matchesStore.bestBets?.bets || [])
// 'value': by edge at the best price. 'safe': favourites by how likely they are to win.
const bestBetsMode = ref('value')
const bestBetsList = computed(() => bestBetsMode.value === 'safe'
  ? bestBets.value.filter(b => b.fairProbability >= 0.5).slice().sort((a, b) => b.fairProbability - a.fairProbability)
  : bestBets.value)
const bestBetsShown = computed(() => bestBetsList.value.slice(0, showAllBestBets.value ? 60 : 8))
const BAND_ORDER = ['50-60', '60-70', '70-80', '80-90', '90-100']
const bandHistoryRows = computed(() => {
  const h = matchesStore.bestBets?.bandHistory || {}
  return ['Match Winner', 'Set 1 Winner'].flatMap(market => BAND_ORDER
    .filter(band => h[market]?.[band])
    .map(band => ({ market, band, ...h[market][band] })))
})
function yieldClass(y) {
  return y >= 0 ? 'text-green-700' : 'text-red-700'
}
const BEST_BET_BADGE = {
  good: { text: 'precio sobre el justo', cls: 'bg-green-100 text-green-800' },
  fair: { text: 'ventaja leve', cls: 'bg-yellow-100 text-yellow-800' },
  check: { text: '🔎 confirma la cuota', cls: 'bg-amber-100 text-amber-800' },
  poor: { text: 'sin ventaja', cls: 'bg-red-100 text-red-800' }
}
function betWhen(b) {
  const day = b.date === getUtcTodayStr() ? 'hoy' : b.date.slice(8, 10) + '/' + b.date.slice(5, 7)
  return `${day} ${b.time}`
}
function betOpinions(b) {
  const out = []
  if (b.engineProbability != null) out.push(`motor ${pct(b.engineProbability)}%`)
  if (b.pointProbability != null) out.push(`modelo de saque y resto ${pct(b.pointProbability)}%` + (b.pointTrust < 0.5 ? ' (poca historia)' : ''))
  return out
}
// The card is the top of that list; without it, the best of the engine's own picks for today.
const pickOfDay = computed(() => {
  const b = bestBets.value[0]
  if (!b) return pickCandidates.value[0] || null
  const parts = [
    b.bestBook
      ? `Mejor cuota: ${b.bestOdds.toFixed(2)} en ${b.bestBook}` + (b.bestOdds > b.referenceOdds ? ` (la de referencia paga ${b.referenceOdds.toFixed(2)}).` : '.')
      : `Cuota ${b.bestOdds.toFixed(2)}.`,
    `Probabilidad justa según la casa de referencia, sin su margen: ${pct(b.fairProbability)}% → edge ${formatEdge(b.edge)}.`
  ]
  const opinions = betOpinions(b)
  if (opinions.length) parts.push(`Segundas opiniones: ${opinions.join(' · ')}.`)
  if (b.level === 'check') parts.push('Esa cuota está muy por encima de la referencia: en el histórico eso casi siempre fue un precio viejo. Confírmala en la casa.')
  if (b.level === 'poor') parts.push('Es el mejor edge disponible, no una ventaja.')
  return {
    level: b.level,
    market: MARKET_ES[b.market] || b.market,
    prediction: b.pick,
    home: b.home,
    away: b.away,
    tournament: b.tournament,
    time: betWhen(b),
    link: b.predictionId ? `/predictions/${b.predictionId}` : `/predictions?matchId=${b.matchId}&date=${b.date}`,
    odd: b.bestOdds,
    prob: b.fairProbability,
    edge: b.edge,
    kelly: b.kelly,
    why: parts.join(' ')
  }
})

// --- Prediction reliability by player + surface (tab "Fiabilidad") ---
const reliabilitySearch = ref('')
const searchFocused = ref(false)
function onSearchBlur() {
  // Delay so a click on a list item registers before the list unmounts.
  setTimeout(() => { searchFocused.value = false }, 150)
}
function pickPlayer(name) {
  reliabilitySearch.value = name
  searchFocused.value = false
}
const SURFACE_ES = { clay: '🟠 Arcilla', hard: '🔵 Dura', grass: '🟢 Hierba' }
function surfaceLabel(s) {
  return SURFACE_ES[s] || s
}
// Career record + Elo per surface: searched server-side (the whole historical
// base is too big to preload), debounced on the same search box.
const SURFACE_BAR = { hard: 'bg-sky-500', clay: 'bg-orange-500', grass: 'bg-green-500' }
function profileMetrics(profile) {
  const pc = (v) => (v == null ? '–' : Math.round(v * 100) + '%')
  const rank = (key) => {
    const r = profile.percentiles?.[key]
    return r == null ? '' : `mejor que el ${r}% del circuito`
  }
  const tb = profile.tiebreaksPlayed
    ? `${profile.tiebreaksWon}-${profile.tiebreaksPlayed - profile.tiebreaksWon}`
    : '–'
  return [
    { label: 'Aces por partido', value: profile.acesPerMatch ?? '–', rank: rank('acesPerMatch') },
    { label: 'Juegos de saque ganados', value: pc(profile.holdPct), rank: rank('holdPct') },
    { label: 'Juegos de resto ganados', value: pc(profile.breakPct), rank: rank('breakPct') },
    { label: 'Puntos con 1er saque', value: pc(profile.firstServeWonPct), rank: rank('firstServeWonPct') },
    { label: 'Tiebreaks (G-P)', value: tb, rank: '' }
  ]
}
const careerLoading = ref(false)
const surfaceCareerPlayers = computed(() => matchesStore.playerSurfaceCareer?.players || [])
let careerTimer = null
watch(reliabilitySearch, (value) => {
  const q = value.trim()
  clearTimeout(careerTimer)
  matchesStore.playerSurfaceCareerQuery = q
  if (q.length < 2) {
    matchesStore.playerSurfaceCareer = null
    careerLoading.value = false
    return
  }
  careerLoading.value = true
  careerTimer = setTimeout(async () => {
    await matchesStore.fetchPlayerSurfaceCareer(q)
    if (matchesStore.playerSurfaceCareerQuery === q) careerLoading.value = false
  }, 400)
})

const reliabilityMinSample = computed(() => matchesStore.predictionReliability?.minSample ?? 4)
const reliabilityOverall = computed(() => matchesStore.predictionReliability?.overall || {})
const reliabilityPlayers = computed(() => matchesStore.predictionReliability?.players || [])

// Every player name with data in either dataset (reliability + points/set),
// sorted — powers the search datalist and the browse-on-focus list.
const allPlayerNames = computed(() => {
  const set = new Set()
  for (const p of reliabilityPlayers.value) set.add(p.player)
  for (const p of matchesStore.playerPointsPerSet?.players || []) set.add(p.player)
  return [...set].sort((a, b) => a.localeCompare(b))
})

const filteredReliabilityPlayers = computed(() => {
  const q = reliabilitySearch.value.trim().toLowerCase()
  if (!q) return []
  return reliabilityPlayers.value.filter((p) => p.player.toLowerCase().includes(q)).slice(0, 30)
})
function rateClass(row, blk) {
  if (blk.best && row.market === blk.best.market) return 'text-green-700'
  if (blk.worst && row.market === blk.worst.market) return 'text-red-700'
  return 'text-slate-700'
}

// Lookup: reliability[playerName][surface] -> { best, worst, markets } for MatchCard
const reliabilityLookup = computed(() => {
  const map = {}
  for (const p of reliabilityPlayers.value) map[p.player] = p.surfaces
  return map
})
function matchReliability(match) {
  const surf = (match.surface || '').toLowerCase()
  const forSide = (name) => {
    const s = reliabilityLookup.value[name]
    return s && surf && s[surf] ? s[surf] : null
  }
  return { player1: forSide(match.player1), player2: forSide(match.player2) }
}

// Average points per set (1..5), shown in the "Fiabilidad" tab. Reuses the
// same player search box; no search -> top by sample size. A surface filter
// switches between the all-surface aggregate and the per-surface breakdown.
const pointsSurface = ref('all')
const pointsPerSetRows = computed(() => {
  const all = matchesStore.playerPointsPerSet?.players || []
  const q = reliabilitySearch.value.trim().toLowerCase()
  const surf = pointsSurface.value
  return all
    .filter((p) => !q || p.player.toLowerCase().includes(q))
    .map((p) => {
      const sets = surf === 'all' ? p.sets : (p.bySurface?.[surf] || {})
      const n = Object.values(sets).reduce((x, s) => x + (s.n || 0), 0)
      return { player: p.player, sets, sampleTotal: n }
    })
    .filter((p) => p.sampleTotal > 0)
    .sort((a, b) => b.sampleTotal - a.sampleTotal)
    .slice(0, q ? 30 : 25)
})

// Last 3 matches per surface, "Fiabilidad" tab. Only shown when searching a
// player (per-match rows for every player would be huge).
const recentBySurfaceRows = computed(() => {
  const all = matchesStore.playerRecentBySurface?.players || []
  const q = reliabilitySearch.value.trim().toLowerCase()
  if (!q) return all.slice(0, 8)
  return all.filter((p) => p.player.toLowerCase().includes(q)).slice(0, 20)
})

function loadToday() {
  return Promise.all([
    matchesStore.fetchByDate(getUtcTodayStr()),
    matchesStore.fetchPlayerSetStats(getUtcTodayStr()),
    matchesStore.fetchPredictionReliability(),
    matchesStore.fetchPlayerPointsPerSet(),
    matchesStore.fetchPlayerRecentBySurface(),
    matchesStore.fetchBestBets(),
    predictionsStore.fetchLatest()
  ])
}

onMounted(async () => {
  await Promise.all([loadToday(), analyticsStore.fetchDashboard()])
  lastLoadedAt.value = new Date()
})
</script>
