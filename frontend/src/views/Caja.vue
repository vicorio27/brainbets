<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-slate-900">Caja</h1>
      <p class="text-sm text-slate-600 mt-1">
        Metes un monto y eliges cómo apostar: te dice cuánto le puedes sacar hoy con las apuestas del día
        y, según el histórico real, en cuántos días se multiplicaría por lo que elijas.
      </p>
    </div>

    <!-- Controles -->
    <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Monto inicial</span>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">$</span>
            <input
              v-model.number="form.initial"
              type="number"
              min="1"
              step="10"
              class="w-full pl-7 pr-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Estrategia de apuesta</span>
          <select
            v-model="form.strategy"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="percent">% de la caja (compuesto)</option>
            <option value="flat">Monto fijo</option>
            <option value="kelly">Kelly fraccionado</option>
          </select>
        </label>

        <label v-if="form.strategy !== 'kelly'" class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            % por apuesta
            <span class="text-slate-400 font-normal">({{ stakeHint }})</span>
          </span>
          <input
            v-model.number="form.stakePct"
            type="number"
            min="0.1"
            max="50"
            step="0.5"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label v-else class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            Fracción de Kelly
            <span class="text-slate-400 font-normal">(0.5 = medio Kelly)</span>
          </span>
          <input
            v-model.number="form.kellyMultiplier"
            type="number"
            min="0.05"
            max="1"
            step="0.05"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            Multiplicar por
            <span class="text-slate-400 font-normal">(→ {{ money(form.initial * form.target) }})</span>
          </span>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">x</span>
            <input
              v-model.number="form.target"
              type="number"
              min="1.1"
              max="100"
              step="0.1"
              list="caja-target-presets"
              class="w-full pl-7 pr-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              @keyup.enter="run"
            />
            <datalist id="caja-target-presets">
              <option value="1.5"></option>
              <option value="2"></option>
              <option value="3"></option>
              <option value="5"></option>
              <option value="10"></option>
            </datalist>
          </div>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Deporte</span>
          <select
            v-model="form.sport"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Todos</option>
            <option value="tennis">🎾 Tenis</option>
            <option value="football">⚽ Fútbol</option>
          </select>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            Mercado
            <span class="text-slate-400 font-normal">("Todos" excluye los en pausa)</span>
          </span>
          <select
            v-model="form.market"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Todos</option>
            <option v-for="m in marketOptions" :key="m" :value="m">{{ marketLabel(m) }}</option>
          </select>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Confianza mínima</span>
          <input
            v-model.number="form.minConfidence"
            type="number"
            min="0"
            max="100"
            step="5"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            Edge mínimo
            <span class="text-slate-400 font-normal">(hoy e histórico)</span>
          </span>
          <select
            v-model="form.minEdge"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Sin filtro (todas)</option>
            <option value="0">Solo edge positivo</option>
            <option value="5">Edge &gt; 5%</option>
            <option value="10">Edge &gt; 10%</option>
          </select>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Histórico</span>
          <select
            v-model.number="form.days"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option :value="30">30 días</option>
            <option :value="90">90 días</option>
            <option :value="180">180 días</option>
            <option :value="365">1 año</option>
            <option :value="1825">Todo</option>
          </select>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Tope por apuesta</span>
          <input
            v-model.number="form.maxStakePct"
            type="number"
            min="0.1"
            max="50"
            step="1"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>

        <div class="flex items-end">
          <button
            @click="run"
            :disabled="store.loading"
            class="w-full px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {{ store.loading ? 'Calculando…' : 'Simular' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="store.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ store.error }}
    </div>

    <div v-else-if="store.loading && !sim" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <template v-else-if="sim">
      <!-- Hoy -->
      <div v-if="today" class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">Con las apuestas de hoy</h2>
        <p v-if="!today.bets" class="text-sm text-slate-500">
          Hoy no hay apuestas con cuota para estos filtros<span v-if="today.withoutOdds">
            ({{ today.withoutOdds }} predicciones sin cuota publicada todavía)</span>.
        </p>
        <template v-else>
          <p class="text-xs text-slate-500 mb-3">
            {{ today.bets }} apuestas ({{ today.notStartedBets }} sin empezar, {{ today.pendingBets - today.notStartedBets }} en juego), poniendo
            {{ money(today.staked) }} en total ({{ today.stakedPct }}% de {{ money(sim.params.initial) }})<span v-if="today.exposureCapped">
              — recortado al tope de 50% de la caja por día</span>.
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <div class="rounded-lg bg-green-50 border border-green-200 p-3">
              <div class="text-xs text-green-800">Si aciertas todas (máximo)</div>
              <div class="text-2xl font-bold text-green-700">+{{ money(today.best.profit) }}</div>
              <div class="text-xs text-green-800">quedas en {{ money(today.best.final) }} ({{ signedPct(today.best.pct) }})</div>
            </div>
            <div class="rounded-lg bg-slate-50 border border-slate-200 p-3">
              <div class="text-xs text-slate-600">Lo esperable según el modelo</div>
              <div class="text-2xl font-bold" :class="today.expected.profit >= 0 ? 'text-green-700' : 'text-red-700'">
                {{ signedMoney(today.expected.profit) }}
              </div>
              <div class="text-xs text-slate-600">quedas en {{ money(today.expected.final) }} ({{ signedPct(today.expected.pct) }})</div>
            </div>
            <div class="rounded-lg bg-red-50 border border-red-200 p-3">
              <div class="text-xs text-red-800">Si fallas todas (mínimo)</div>
              <div class="text-2xl font-bold text-red-700">{{ signedMoney(today.worst.profit) }}</div>
              <div class="text-xs text-red-800">quedas en {{ money(today.worst.final) }} ({{ signedPct(today.worst.pct) }})</div>
            </div>
          </div>
          <p v-if="today.bets > today.pendingBets" class="text-sm text-slate-700 mb-3">
            Ya resueltas hoy: <strong :class="today.realized.profit >= 0 ? 'text-green-700' : 'text-red-700'">{{ signedMoney(today.realized.profit) }}</strong>
            · todavía en juego {{ money(today.pendingStaked) }}.
          </p>
          <details>
            <summary class="text-sm text-blue-700 cursor-pointer">Ver cuánto poner en cada una</summary>
            <div class="overflow-x-auto mt-2" tabindex="0">
              <table class="min-w-full text-sm">
                <thead>
                  <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                    <th class="py-2 pr-4">Partido</th>
                    <th class="py-2 px-3">Apuesta</th>
                    <th class="py-2 px-3">Cuota</th>
                    <th class="py-2 px-3">Prob.</th>
                    <th class="py-2 px-3">Edge</th>
                    <th class="py-2 px-3">Poner</th>
                    <th class="py-2 px-3">Si gana</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in today.items" :key="item.predictionId" class="border-t border-slate-100">
                    <td class="py-2 pr-4 whitespace-nowrap">
                      <router-link :to="`/predictions/${item.predictionId}`" class="font-medium text-slate-900 hover:text-blue-700">
                        {{ item.sport === 'tennis' ? '🎾' : '⚽' }} {{ item.match }}
                      </router-link>
                      <span class="block text-xs text-slate-500">{{ item.time }} · {{ item.league }}</span>
                    </td>
                    <td class="py-2 px-3 text-slate-700">
                      {{ item.selection }}
                      <span class="block text-xs text-slate-500">{{ item.market }}</span>
                    </td>
                    <td class="py-2 px-3 text-slate-600">{{ item.odds }}</td>
                    <td class="py-2 px-3 text-slate-600">{{ item.probability }}%</td>
                    <td class="py-2 px-3 font-medium" :class="item.edge >= 0 ? 'text-green-700' : 'text-red-700'">{{ signedPct(item.edge) }}</td>
                    <td class="py-2 px-3 font-semibold text-slate-900">{{ money(item.stake) }}</td>
                    <td class="py-2 px-3 whitespace-nowrap">
                      <span v-if="item.won === true" class="text-green-700 font-medium">✅ +{{ money(item.winProfit) }}</span>
                      <span v-else-if="item.won === false" class="text-red-700 font-medium">❌ -{{ money(item.stake) }}</span>
                      <span v-else class="text-green-700">
                        +{{ money(item.winProfit) }}
                        <span v-if="item.started" class="text-xs text-amber-700">· en juego</span>
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
          <p class="text-xs text-slate-500 mt-3">
            El máximo exige acertar todas a la vez, casi nunca pasa. "Lo esperable" usa la probabilidad calibrada del
            modelo, y el histórico de abajo dice que ningún mercado tiene todavía una ventaja demostrada: tómalo como
            orientación, no como ganancia asegurada.
            <span v-if="today.withoutOdds">{{ today.withoutOdds }} predicciones de hoy quedan fuera por no tener cuota.</span>
            <span v-if="today.skippedNoStake"> {{ today.skippedNoStake }} sin ventaja según Kelly no se apuestan.</span>
          </p>
        </template>
      </div>

      <!-- Agresivo: todo a una -->
      <div v-if="aggressive" class="rounded-lg border border-amber-300 bg-amber-50 p-4 mb-6">
        <h2 class="text-lg font-semibold text-amber-900 mb-1">ðŸ”¥ Modo agresivo: todo a una</h2>
        <p v-if="!aggressive.pick" class="text-sm text-amber-900">
          Hoy no queda ninguna apuesta con cuota en un partido que no haya empezado.
        </p>
        <template v-else>
          <p class="text-sm text-amber-900">
            <template v-if="aggressive.note === 'sin_edge_positivo'">
              <strong>Hoy ninguna apuesta tiene edge positivo.</strong> La menos mala serÃ­a
            </template>
            <template v-else>La mejor apuesta de hoy ({{ aggressive.positiveEdgeBets }} con edge positivo) es</template>
            <router-link :to="`/predictions/${aggressive.pick.predictionId}`" class="font-semibold underline">
              {{ aggressive.pick.selection }} â€” {{ aggressive.pick.market }}
            </router-link>
            en {{ aggressive.pick.match }} ({{ aggressive.pick.time }}, {{ aggressive.pick.league }}):
            cuota {{ aggressive.pick.odds }}, probabilidad {{ aggressive.pick.probability }}%,
            edge <span :class="aggressive.pick.edge > 0 ? 'text-green-700' : 'text-red-700'" class="font-semibold">{{ signedPct(aggressive.pick.edge) }}</span>.
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            <div class="rounded-lg bg-white border border-amber-200 p-3">
              <div class="text-xs text-slate-600">Metiendo los {{ money(aggressive.allIn.stake) }} completos hoy</div>
              <div class="text-xl font-bold text-slate-900">
                {{ money(aggressive.allIn.stake) }} â†’ {{ money(aggressive.allIn.finalIfWin) }}
                <span class="text-sm font-medium text-slate-600">(x{{ aggressive.allIn.multipleIfWin }})</span>
              </div>
              <div class="text-sm mt-1">
                <span class="text-green-700 font-semibold">{{ aggressive.allIn.probWin }}% de lograrlo</span> Â·
                <span class="text-red-700 font-semibold">{{ aggressive.allIn.probLoseAll }}% de quedar en ceros</span>
              </div>
            </div>
            <div class="rounded-lg bg-white border border-amber-200 p-3">
              <div class="text-xs text-slate-600">
                Para llegar a x{{ aggressive.targetMultiple }}
                <template v-if="aggressive.chain.steps > 1">reinvirtiendo todo en apuestas como esta</template>
              </div>
              <div class="text-xl font-bold text-slate-900">
                {{ aggressive.chain.steps }} {{ aggressive.chain.steps === 1 ? 'acierto' : 'aciertos seguidos' }}
                <span class="text-sm font-medium text-slate-600">
                  (~{{ aggressive.chain.days }} {{ aggressive.chain.days === 1 ? 'dÃ­a' : 'dÃ­as' }}, quedas en {{ money(aggressive.chain.finalIfAllWin) }})
                </span>
              </div>
              <div class="text-sm mt-1">
                <span class="text-green-700 font-semibold">{{ aggressive.chain.probAllWin }}% de lograrlo</span> Â·
                <span class="text-red-700 font-semibold">{{ aggressive.chain.probLoseAll }}% de quedar en ceros</span>
              </div>
            </div>
          </div>
          <p class="text-xs text-amber-900 mt-3">
            Ignora la estrategia y los topes de arriba: es todo o nada. Para esta misma apuesta Kelly recomendarÃ­a poner
            {{ aggressive.pick.kellyPct }}% de la caja, no el 100%. Las probabilidades son las del modelo, que todavÃ­a no
            tiene una ventaja demostrada en ningÃºn mercado; la cadena asume encontrar cada dÃ­a una apuesta con la misma
            cuota y probabilidad.
          </p>
        </template>
      </div>

      <!-- Veredicto -->
      <div class="rounded-lg border p-5 mb-6" :class="verdict.box">
        <div class="flex items-start gap-3">
          <div class="text-3xl">{{ verdict.icon }}</div>
          <div>
            <h2 class="text-lg font-semibold" :class="verdict.title">{{ verdict.headline }}</h2>
            <p class="text-sm mt-1" :class="verdict.text">{{ verdict.detail }}</p>
          </div>
        </div>
      </div>

      <div v-if="!sim.backtest.bets" class="bg-white rounded-lg shadow-sm border border-slate-200 p-8 text-center text-slate-500">
        No hay apuestas resueltas con cuota guardada para estos filtros.
      </div>

      <template v-else>
        <!-- KPIs -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KpiCard title="Caja final (histórico)" :value="money(sim.backtest.final)" :color="sim.backtest.profit >= 0 ? 'green' : 'red'" icon="💰" />
          <KpiCard title="Yield por apuesta" :value="signedPct(sim.backtest.yield)" :color="sim.backtest.yield >= 0 ? 'green' : 'red'" icon="📈" />
          <KpiCard title="Aciertos" :value="pct(sim.backtest.winRate)" icon="🎯" />
          <KpiCard title="Caída máxima" :value="pct(sim.backtest.maxDrawdown)" :color="sim.backtest.maxDrawdown > 30 ? 'red' : 'yellow'" icon="📉" />
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <!-- Curva -->
          <div class="lg:col-span-2 bg-white rounded-lg shadow-sm border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-900 mb-1">Evolución de la caja</h2>
            <p class="text-xs text-slate-500 mb-3">
              {{ sim.backtest.bets }} apuestas resueltas entre {{ sim.sample.firstDate }} y {{ sim.sample.lastDate }}
              ({{ sim.backtest.betsPerDay }} por día).
            </p>
            <svg v-if="chart" :viewBox="`0 0 ${chart.w} ${chart.h}`" class="w-full h-56" preserveAspectRatio="none" role="img" aria-label="Curva de la caja">
              <line :x1="0" :x2="chart.w" :y1="chart.baseY" :y2="chart.baseY" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 4" />
              <polygon :points="chart.area" :fill="chart.positive ? '#dcfce7' : '#fee2e2'" />
              <polyline :points="chart.line" fill="none" :stroke="chart.positive ? '#16a34a' : '#dc2626'" stroke-width="2" />
            </svg>
            <div class="flex justify-between text-xs text-slate-500 mt-1">
              <span>{{ money(sim.backtest.initial) }} inicial</span>
              <span>{{ money(sim.backtest.final) }} final</span>
            </div>
          </div>

          <!-- Monte Carlo -->
          <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-900 mb-1">Simulación a futuro</h2>
            <p class="text-xs text-slate-500 mb-3">
              {{ sim.monteCarlo.sims || 0 }} escenarios remuestreando el histórico, horizonte
              {{ sim.monteCarlo.horizonDays || 0 }} días.
            </p>
            <dl v-if="sim.monteCarlo.sims" class="space-y-2 text-sm">
              <div class="flex justify-between">
                <dt class="text-slate-600">Prob. de llegar a x{{ sim.params.targetMultiple }}</dt>
                <dd class="font-semibold" :class="sim.monteCarlo.probReachTarget >= 50 ? 'text-green-700' : 'text-amber-700'">
                  {{ sim.monteCarlo.probReachTarget }}%
                </dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-600">Prob. de quebrar la caja</dt>
                <dd class="font-semibold" :class="sim.monteCarlo.probRuin > 20 ? 'text-red-700' : 'text-slate-900'">
                  {{ sim.monteCarlo.probRuin }}%
                </dd>
              </div>
              <div class="flex justify-between border-t border-slate-100 pt-2">
                <dt class="text-slate-600">1 de cada 10 escenarios llega en</dt>
                <dd class="font-semibold text-slate-900">{{ days(sim.monteCarlo.daysP10) }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-600">La mitad llega en</dt>
                <dd class="font-semibold text-slate-900">{{ days(sim.monteCarlo.daysP50) }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-slate-600">9 de cada 10 llegan en</dt>
                <dd class="font-semibold text-slate-900">{{ days(sim.monteCarlo.daysP90) }}</dd>
              </div>
              <div v-if="sim.monteCarlo.daysP50 == null && sim.monteCarlo.daysP50IfReached != null" class="flex justify-between">
                <dt class="text-slate-600">Mediana solo entre los que llegan</dt>
                <dd class="font-semibold text-slate-900">{{ days(sim.monteCarlo.daysP50IfReached) }}</dd>
              </div>
              <div class="flex justify-between border-t border-slate-100 pt-2">
                <dt class="text-slate-600">Caja mediana al final</dt>
                <dd class="font-semibold text-slate-900">{{ money(sim.monteCarlo.finalP50) }}</dd>
              </div>
            </dl>
            <p v-else class="text-sm text-slate-500">Sin datos suficientes.</p>
          </div>
        </div>

        <!-- Por mercado -->
        <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
          <h2 class="text-lg font-semibold text-slate-900 mb-1">Qué mercados pagan</h2>
          <p class="text-xs text-slate-500 mb-3">
            Yield con apuesta plana de 1 unidad. "Señal" es un test estadístico sobre esa ganancia media
            (no solo si quedó positiva): exige ≥30 apuestas y que el intervalo de confianza del 95% no
            cruce el cero. Si dice "no concluyente", el yield puede ser puro ruido — probar con más datos
            antes de confiar la caja a ese mercado.
          </p>
          <div class="overflow-x-auto" tabindex="0">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-2 pr-4">Mercado</th>
                  <th class="py-2 px-3">Apuestas</th>
                  <th class="py-2 px-3">Aciertos</th>
                  <th class="py-2 px-3">Cuota media</th>
                  <th class="py-2 px-3">Unidades</th>
                  <th class="py-2 px-3">Yield (IC 95%)</th>
                  <th class="py-2 px-3">Señal</th>
                  <th class="py-2 px-3">
                    CLV
                    <span class="normal-case text-slate-400 font-normal block text-[10px]">vs. cuota de cierre</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in sim.byMarket" :key="row.sport + row.market" class="border-t border-slate-100">
                  <td class="py-2 pr-4 font-medium text-slate-900 whitespace-nowrap">
                    {{ row.sport === 'tennis' ? '🎾' : '⚽' }} {{ row.market }}
                  </td>
                  <td class="py-2 px-3 text-slate-600">{{ row.bets }}</td>
                  <td class="py-2 px-3 text-slate-600">{{ row.wins }} ({{ row.winRate }}%)</td>
                  <td class="py-2 px-3 text-slate-600">{{ row.avgOdds }}</td>
                  <td class="py-2 px-3 font-medium" :class="row.profitUnits >= 0 ? 'text-green-700' : 'text-red-700'">
                    {{ row.profitUnits > 0 ? '+' : '' }}{{ row.profitUnits }}
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <span class="font-semibold" :class="row.yield >= 0 ? 'text-green-700' : 'text-red-700'">
                      {{ signedPct(row.yield) }}
                    </span>
                    <span class="text-xs text-slate-500">
                      ({{ signedPct(row.yieldCiLow) }} a {{ signedPct(row.yieldCiHigh) }})
                    </span>
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <span
                      v-if="row.significant && row.yield > 0"
                      class="inline-flex items-center gap-1 text-green-700 font-medium"
                      title="≥30 apuestas y el intervalo de confianza del 95% no cruza el cero"
                    >✅ edge real</span>
                    <span
                      v-else-if="row.significant"
                      class="inline-flex items-center gap-1 text-red-700 font-medium"
                      title="≥30 apuestas y el intervalo de confianza del 95% confirma pérdida"
                    >🛑 pérdida real</span>
                    <span v-else class="inline-flex items-center gap-1 text-slate-500" title="El intervalo de confianza cruza el cero: no se puede distinguir de ruido">
                      ❓ no concluyente
                    </span>
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <template v-if="row.clvSamples">
                      <span class="font-semibold" :class="row.avgClv >= 0 ? 'text-green-700' : 'text-red-700'">
                        {{ signedPct(row.avgClv) }}
                      </span>
                      <span class="text-xs text-slate-500">
                        ({{ row.positiveClvPct }}% le ganó al cierre, n={{ row.clvSamples }})
                      </span>
                    </template>
                    <span v-else class="text-xs text-slate-400">sin datos aún</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-xs text-slate-500 mt-3">
            <strong>CLV (Closing Line Value):</strong> compara la cuota que usamos contra la cuota justo antes de que
            arrancara el partido. Positivo significa que conseguimos mejor precio que el mercado al cierre — es la señal
            de edge real más rápida que existe, no necesita cientos de apuestas como el yield para dejar de ser ruido,
            porque cada apuesta aporta un número real en vez de solo ganar/perder. Captura automática desde el
            {{ clvSince }}; todavía hay poca muestra.
          </p>
        </div>

        <!-- Consistencia en el tiempo -->
        <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mb-6">
          <h2 class="text-lg font-semibold text-slate-900 mb-1">¿El edge se sostiene en el tiempo?</h2>
          <p class="text-xs text-slate-500 mb-3">
            Cada mercado partido en dos mitades por fecha. Un edge real debería ganar plata en las dos mitades,
            no solo en el promedio — si todo el yield viene de una sola mitad, lo más probable es que haya sido
            una racha, no una ventaja que se sostiene.
          </p>
          <div class="overflow-x-auto" tabindex="0">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-2 pr-4">Mercado</th>
                  <th class="py-2 px-3">1ª mitad</th>
                  <th class="py-2 px-3">2ª mitad</th>
                  <th class="py-2 px-3">¿Consistente?</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in sim.stability" :key="row.sport + row.market" class="border-t border-slate-100">
                  <td class="py-2 pr-4 font-medium text-slate-900 whitespace-nowrap">
                    {{ row.sport === 'tennis' ? '🎾' : '⚽' }} {{ row.market }}
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <span class="font-semibold" :class="row.firstHalf.yield >= 0 ? 'text-green-700' : 'text-red-700'">
                      {{ signedPct(row.firstHalf.yield) }}
                    </span>
                    <span class="text-xs text-slate-500">({{ row.firstHalf.bets }}, {{ row.firstHalf.from }})</span>
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <span class="font-semibold" :class="row.secondHalf.yield >= 0 ? 'text-green-700' : 'text-red-700'">
                      {{ signedPct(row.secondHalf.yield) }}
                    </span>
                    <span class="text-xs text-slate-500">({{ row.secondHalf.bets }}, desde {{ row.secondHalf.from }})</span>
                  </td>
                  <td class="py-2 px-3 whitespace-nowrap">
                    <span v-if="row.consistent" class="text-green-700 font-medium">✅ gana en ambas mitades</span>
                    <span v-else class="text-slate-500">⚠️ no sostenido</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="sim.stability && sim.stability.length && !sim.stability.some(r => r.consistent)" class="text-xs text-amber-700 mt-3">
            Ningún mercado gana en las dos mitades de su historial todavía — ni siquiera el que muestra mejor yield general.
          </p>
        </div>
      </template>

      <!-- Advertencias -->
      <div class="bg-slate-100 border border-slate-200 rounded-lg p-4 text-xs text-slate-600 space-y-1">
        <p>
          <strong>Muestra:</strong> {{ sim.sample.settledPredictions }} predicciones ya validadas en la ventana;
          solo {{ sim.sample.withOdds }} ({{ sim.sample.oddsCoverage ?? 0 }}%) tienen cuota guardada y entran a la simulación.
          Las {{ sim.sample.withoutOdds }} restantes se ignoran porque sin cuota no se sabe cuánto habrían pagado.
          <span v-if="sim.sample.afterStart">
            {{ sim.sample.afterStart }} predicciones se descartan porque se generaron con el partido ya empezado:
            no eran apuestas que se pudieran hacer.
          </span>
          <span v-if="sim.sample.belowMinEdge">
            Otras {{ sim.sample.belowMinEdge }} tenían cuota pero quedaron fuera por el filtro de edge mínimo.
          </span>
        </p>
        <p v-if="smallSample">
          <strong>Ojo:</strong> con menos de 100 apuestas el resultado es ruido tanto como señal. Los días proyectados
          pueden cambiar mucho con unos pocos partidos más.
        </p>
        <p v-if="filterSignal && !filterSignal.significant">
          <strong>Importante:</strong> el mercado que filtraste ({{ filterSignal.market }}) no pasa el test de
          significancia — su intervalo de confianza del 95% ({{ signedPct(filterSignal.yieldCiLow) }} a
          {{ signedPct(filterSignal.yieldCiHigh) }}) cruza el cero. El yield positivo que ves puede desaparecer
          con más partidos; no apuestes dinero real contra esta proyección todavía.
        </p>
        <p>
          Es un backtest, no una promesa: asume que consigues las mismas cuotas, que el modelo sigue rindiendo igual,
          y no descuenta comisiones ni límites de casa de apuestas.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, onMounted } from 'vue'
import { useBankrollStore } from '../stores/bankroll.js'
import KpiCard from '../components/KpiCard.vue'

const store = useBankrollStore()

const marketOptions = [
  'Match Winner',
  'Set 1 Winner',
  'Total Sets',
  'Exact Set Score',
  'Total Aces',
  'Over/Under 2.5 Goals',
  'Both Teams To Score'
]
// Markets excluded from the DEFAULT ("Todos") universe on the backend
// (see bankroll_service.PAUSED_BETTING_MARKETS) -- selecting one here
// explicitly still works, for monitoring while it's under redesign.
const PAUSED_MARKETS = new Set(['Exact Set Score'])
function marketLabel(m) {
  return PAUSED_MARKETS.has(m) ? `${m} (en pausa)` : m
}

const form = reactive({
  initial: 100,
  strategy: 'percent',
  stakePct: 2,
  kellyMultiplier: 0.5,
  maxStakePct: 10,
  target: 2,
  sport: '',
  market: '',
  minConfidence: 0,
  minEdge: '0',
  days: 365
})

const sim = computed(() => store.simulation)
const today = computed(() => sim.value?.today || null)
const aggressive = computed(() => today.value?.aggressive || null)
const smallSample = computed(() => (sim.value?.backtest?.bets || 0) < 100)
// When the user filters to one specific market, surface whether THAT market's
// yield is statistically distinguishable from noise (not just positive).
const filterSignal = computed(() => {
  if (!sim.value?.params?.market) return null
  return (sim.value.byMarket || []).find((r) => r.market === sim.value.params.market) || null
})
// CLV capture (validation_db's new "Capture Closing Odds" node) started 2026-10-02.
const clvSince = '2 de octubre'

const stakeHint = computed(() =>
  form.strategy === 'flat' ? 'sobre el monto inicial' : 'sobre la caja actual'
)

function money(value) {
  if (value == null) return '–'
  return '$' + Number(value).toLocaleString('es-CO', { maximumFractionDigits: 2 })
}
function signedMoney(value) {
  if (value == null) return '–'
  return (value < 0 ? '-' : '+') + money(Math.abs(value))
}
function pct(value) {
  if (value == null) return '–'
  return `${value}%`
}
// Signed: yields and ROIs read better with an explicit + when positive.
function signedPct(value) {
  if (value == null) return '–'
  return `${value > 0 ? '+' : ''}${value}%`
}
function days(value) {
  if (value == null) return 'no llega'
  return `${Math.round(value)} días`
}

const verdict = computed(() => {
  const s = sim.value
  if (!s) return {}
  const p = s.projection
  const target = `x${s.params.targetMultiple}`
  const amount = money(p.targetAmount)
  const good = {
    box: 'bg-green-50 border-green-200',
    title: 'text-green-900',
    text: 'text-green-800',
    icon: '🚀'
  }
  const bad = {
    box: 'bg-red-50 border-red-200',
    title: 'text-red-900',
    text: 'text-red-800',
    icon: '🛑'
  }
  const warn = {
    box: 'bg-amber-50 border-amber-200',
    title: 'text-amber-900',
    text: 'text-amber-800',
    icon: '⚠️'
  }
  const neutral = {
    box: 'bg-slate-50 border-slate-200',
    title: 'text-slate-900',
    text: 'text-slate-700',
    icon: 'ℹ️'
  }

  if (p.note === 'sin_datos') {
    return {
      ...neutral,
      headline: 'Todavía no hay con qué calcular',
      detail: 'No hay apuestas resueltas con cuota guardada para estos filtros. Prueba ampliando el histórico o quitando filtros.'
    }
  }
  if (p.note === 'sin_ventaja') {
    return {
      ...bad,
      headline: `Con esta configuración la caja no crece: nunca llegas a ${target}`,
      detail: `En el histórico, ${money(s.params.initial)} habrían terminado en ${money(s.backtest.final)} (yield ${signedPct(s.backtest.yield)}). Filtra por los mercados que sí pagan en la tabla de abajo antes de meter dinero real.`
    }
  }
  const v = s.verdict || {}
  const mc = s.monteCarlo || {}
  const edge = v.edge || {}
  const odds = mc.sims
    ? ` En la simulación, ${mc.probReachTarget}% de los escenarios llega a ${target} en ${mc.horizonDays} días y ${mc.probRuin}% quiebra antes.`
    : ''
  const history =
    p.note === 'ya_alcanzado'
      ? `En el histórico, ${money(s.params.initial)} llegaron a ${money(s.backtest.final)} en ${s.backtest.daysSpan} días.`
      : p.note === 'horizonte_excedido'
        ? `El histórico crece ${p.dailyGrowthPct}% diario: a ese ritmo ${target} tomaría años.`
        : `Al ritmo del histórico (${p.dailyGrowthPct}% diario) serían ~${Math.round(p.daysToTarget)} días.`

  if (v.level === 'edge_real') {
    const typical = mc.daysP50 != null ? `~${Math.round(mc.daysP50)} días` : `~${Math.round(p.daysToTarget)} días`
    return {
      ...good,
      headline:
        p.note === 'ya_alcanzado'
          ? `El histórico ya superó ${target}`
          : `${money(s.params.initial)} → ${amount} en ${typical}`,
      detail: `${history}${odds} El yield (${signedPct(edge.yield)}, IC 95% ${signedPct(edge.yieldCiLow)} a ${signedPct(edge.yieldCiHigh)}) se distingue del azar con ${edge.bets} apuestas.`
    }
  }

  const why = []
  const reasons = v.reasons || []
  if (reasons.includes('muestra_chica')) why.push(`solo hay ${edge.bets} apuestas, muy pocas para concluir algo`)
  if (reasons.includes('yield_no_significativo'))
    why.push(`el yield (${signedPct(edge.yield)}, IC 95% ${signedPct(edge.yieldCiLow)} a ${signedPct(edge.yieldCiHigh)}) no se distingue del azar`)
  if (reasons.includes('mayoria_no_llega')) why.push('la mayoría de los escenarios simulados no llega')
  if (reasons.includes('riesgo_quiebra')) why.push('el riesgo de quebrar es alto')
  if (reasons.includes('demasiado_lento')) why.push('el crecimiento es demasiado lento')
  return {
    ...warn,
    headline: `No hay base para prometer ${target}`,
    detail: `${history}${odds} No lo tomes como pronóstico: ${why.join('; ') || 'la evidencia es insuficiente'}.`
  }
})

const chart = computed(() => {
  const curve = sim.value?.backtest?.curve || []
  if (curve.length < 2) return null
  const w = 600
  const h = 200
  const initial = sim.value.backtest.initial
  const values = curve.map((p) => p.bankroll).concat([initial])
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (i) => (i / (curve.length - 1)) * w
  const y = (v) => h - ((v - min) / span) * (h - 10) - 5
  const points = curve.map((p, i) => `${x(i).toFixed(1)},${y(p.bankroll).toFixed(1)}`)
  const baseY = y(initial)
  return {
    w,
    h,
    baseY: baseY.toFixed(1),
    line: points.join(' '),
    area: `0,${baseY.toFixed(1)} ${points.join(' ')} ${w},${baseY.toFixed(1)}`,
    positive: curve[curve.length - 1].bankroll >= initial
  }
})

function run() {
  const params = {
    initial: form.initial,
    strategy: form.strategy,
    stakePct: form.stakePct,
    kellyMultiplier: form.kellyMultiplier,
    maxStakePct: form.maxStakePct,
    target: form.target,
    days: form.days,
    minConfidence: form.minConfidence
  }
  if (form.sport) params.sport = form.sport
  if (form.market) params.market = form.market
  if (form.minEdge !== '') params.minEdge = Number(form.minEdge)
  store.simulate(params)
}

onMounted(run)
</script>
