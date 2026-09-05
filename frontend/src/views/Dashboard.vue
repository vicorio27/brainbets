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
                  :class="pick.edge > 0.05
                    ? 'bg-green-100 text-green-700 border border-green-200'
                    : pick.edge > 0
                      ? 'bg-amber-100 text-amber-700 border border-amber-200'
                      : 'bg-slate-100 text-slate-600 border border-slate-200'"
                  class="text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap"
                  :title="pick.kelly != null ? `Kelly: ${(pick.kelly * 100).toFixed(1)}% · stake sugerido = ¼ Kelly. Solo apostar si edge > 5%.` : ''"
                >
                  edge {{ (pick.edge * 100).toFixed(0) }}%
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
          ? 'Ningún pick de hoy supera ese edge. Baja el filtro o espera a que lleguen más cuotas (collect).'
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
              message="No hay partidos disponibles para hoy."
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
import { ref, computed, onMounted } from 'vue'
import { useMatchesStore } from '../stores/matches.js'
import { usePredictionsStore } from '../stores/predictions.js'
import { useAnalyticsStore } from '../stores/analytics.js'
import MatchCard from '../components/MatchCard.vue'
import EmptyState from '../components/EmptyState.vue'

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
    if (p.eventDate && p.eventDate !== today) continue
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
      edge: p.expectedValue ?? null,
      kelly: p.kellyFraction ?? null
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
  // Exact Set Score's "confidence" is already P(scoreline); its calibrated
  // value is meaningless (binary curve). Everything else uses calibrated.
  const c = p.market === 'Exact Set Score' ? p.confidence : (p.calibratedConfidence ?? p.confidence)
  return c != null ? c / 100 : null
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
    predictionsStore.fetchLatest()
  ])
}

onMounted(async () => {
  await Promise.all([loadToday(), analyticsStore.fetchDashboard()])
  lastLoadedAt.value = new Date()
})
</script>
