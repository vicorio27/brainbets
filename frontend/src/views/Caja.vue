<template>
  <div>
    <div class="mb-5">
      <h1 class="text-2xl font-bold text-slate-900">Caja</h1>
      <p class="text-sm text-slate-600 mt-1">
        Cuánto le puedes sacar a tu monto hoy y, según el histórico real, en cuántos días se multiplicaría.
      </p>
    </div>

    <!-- Controles -->
    <div class="bg-white rounded-xl border border-slate-200 p-4 mb-5">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Monto inicial</span>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">$</span>
            <input
              v-model.number="form.initial"
              type="number"
              min="1"
              step="10"
              class="w-full pl-7 pr-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              @keyup.enter="run"
            />
          </div>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">Mercado</span>
          <select
            v-model="form.market"
            class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            @change="run"
          >
            <option value="">Todos los activos</option>
            <option v-for="m in marketOptions" :key="m" :value="m">{{ marketLabel(m) }}</option>
          </select>
        </label>

        <label class="text-sm">
          <span class="block font-medium text-slate-700 mb-1">
            Multiplicar por
            <span class="text-slate-500 font-normal">(→ {{ money(form.initial * form.target) }})</span>
          </span>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">x</span>
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

      <details class="mt-3">
        <summary class="text-sm text-slate-600 cursor-pointer select-none">
          Ajustes avanzados
          <span class="text-slate-500">· {{ advancedSummary }}</span>
        </summary>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-3">
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
              <span class="text-slate-500 font-normal">({{ stakeHint }})</span>
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
              <span class="text-slate-500 font-normal">(0.5 = medio Kelly)</span>
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
            <span class="block font-medium text-slate-700 mb-1">Tope por apuesta (%)</span>
            <input
              v-model.number="form.maxStakePct"
              type="number"
              min="0.1"
              max="50"
              step="1"
              class="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>

          <label class="text-sm">
            <span class="block font-medium text-slate-700 mb-1">
              Edge mínimo
              <span class="text-slate-500 font-normal">(hoy e histórico)</span>
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
        </div>
        <p class="text-xs text-slate-500 mt-2">Cambia lo que quieras y pulsa Simular.</p>
      </details>
    </div>

    <div v-if="store.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ store.error }}
    </div>

    <div v-else-if="store.loading && !sim" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <template v-else-if="sim">
      <!-- Veredicto -->
      <div class="bg-white rounded-xl border border-slate-200 border-l-4 p-5 mb-5" :class="verdict.accent">
        <p class="text-xs uppercase tracking-wide text-slate-500 mb-1">
          {{ sim.params.market ? marketLabel(sim.params.market) : 'Todos los mercados activos' }}
        </p>
        <h2 class="text-lg font-semibold text-slate-900">{{ verdict.icon }} {{ verdict.headline }}</h2>
        <p class="text-sm text-slate-700 mt-1">{{ verdict.detail }}</p>
      </div>

      <!-- Categorías: una a la vez -->
      <div class="flex gap-1 mb-4 border-b border-slate-200 overflow-x-auto" role="tablist" aria-label="Secciones de la Caja">
        <button
          v-for="t in tabs"
          :key="t.id"
          type="button"
          role="tab"
          :aria-selected="tab === t.id"
          class="px-3 sm:px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px"
          :class="tab === t.id ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-600 hover:text-slate-900'"
          @click="tab = t.id"
        >
          {{ t.label }}
          <span v-if="t.hint" class="text-xs font-normal text-slate-500">{{ t.hint }}</span>
        </button>
      </div>

      <!-- Caja por mercado -->
      <div v-if="marketCajas.length" v-show="tab === 'mercados'" class="bg-white rounded-xl border border-slate-200 p-4 mb-5">
        <h2 class="text-lg font-semibold text-slate-900">Caja por mercado</h2>
        <p class="text-xs text-slate-500 mb-3">
          Lo que habrían hecho {{ money(sim.params.initial) }} en cada mercado por separado, con los mismos ajustes.
          Toca un mercado para ver todo lo de abajo solo con él.
        </p>
        <div class="overflow-x-auto" tabindex="0" role="region" aria-label="Caja por mercado">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-4">Mercado</th>
                <th class="py-2 px-3">Caja final</th>
                <th class="py-2 px-3">Yield</th>
                <th class="py-2 px-3">Apuestas</th>
                <th class="py-2 px-3">Aciertos</th>
                <th class="py-2 px-3">Caída máx.</th>
                <th class="py-2 px-3">Llega a x{{ sim.params.targetMultiple }}</th>
                <th class="py-2 px-3">Veredicto</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in marketCajas"
                :key="(row.sport || '') + (row.market || 'all')"
                class="border-t border-slate-100 cursor-pointer hover:bg-slate-50"
                :class="isSelected(row) ? 'bg-blue-50 hover:bg-blue-50' : ''"
                @click="selectMarket(row)"
              >
                <td class="py-2 pr-4 whitespace-nowrap">
                  <button type="button" class="font-medium text-slate-900 text-left hover:text-blue-700" @click.stop="selectMarket(row)">
                    <template v-if="row.market">{{ row.sport === 'tennis' ? '🎾' : '⚽' }} {{ row.market }}</template>
                    <template v-else>Todos los activos</template>
                  </button>
                  <span v-if="row.paused" class="ml-1 text-xs text-slate-500">(en pausa)</span>
                  <!-- On a phone the verdict column is off-screen: repeat it here. -->
                  <span class="block sm:hidden mt-1">
                    <span class="inline-block rounded-full px-2 py-0.5 text-xs font-medium" :class="levelBadge(row.level).cls">
                      {{ levelBadge(row.level).text }}
                    </span>
                  </span>
                </td>
                <td class="py-2 px-3 font-semibold whitespace-nowrap" :class="row.profit >= 0 ? 'text-green-700' : 'text-red-700'">
                  {{ money(row.final) }}
                </td>
                <td class="py-2 px-3 whitespace-nowrap" :class="row.yield >= 0 ? 'text-green-700' : 'text-red-700'">
                  {{ signedPct(row.yield) }}
                </td>
                <td class="py-2 px-3 text-slate-600">{{ row.bets }}</td>
                <td class="py-2 px-3 text-slate-600">{{ pct(row.winRate) }}</td>
                <td class="py-2 px-3 text-slate-600">{{ pct(row.maxDrawdown) }}</td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  {{ pct(row.probReachTarget) }}
                  <span v-if="row.probRuin" class="text-xs text-slate-500">· quiebra {{ row.probRuin }}%</span>
                </td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <span class="inline-block rounded-full px-2 py-0.5 text-xs font-medium" :class="levelBadge(row.level).cls">
                    {{ levelBadge(row.level).text }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-xs text-slate-500 mt-2">
          "Llega a x{{ sim.params.targetMultiple }}" es el % de escenarios simulados que lo logra en
          {{ sim.monteCarlo.horizonDays || 365 }} días. "Todos los activos" no incluye los mercados en pausa.
        </p>
      </div>

      <!-- Hoy -->
      <div v-if="today" v-show="tab === 'hoy'" class="bg-white rounded-xl border border-slate-200 p-4 mb-5">
        <h2 class="text-lg font-semibold text-slate-900 mb-1">Con las apuestas de hoy</h2>
        <p v-if="!today.bets" class="text-sm text-slate-500">
          Hoy no hay apuestas con cuota para estos filtros<span v-if="today.withoutOdds">
            ({{ today.withoutOdds }} predicciones sin cuota publicada todavía)</span>.
        </p>
        <template v-else>
          <p class="text-xs text-slate-500 mb-3">
            {{ today.bets }} apuestas ({{ today.notStartedBets }} sin empezar, {{ today.pendingBets - today.notStartedBets }} en juego,
            {{ today.bets - today.pendingBets }} resueltas), poniendo
            {{ money(today.staked) }} en total ({{ today.stakedPct }}% de {{ money(sim.params.initial) }})<span v-if="today.exposureCapped">
              — recortado al tope de 50% de la caja por día</span>.
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-100 mb-3">
            <div class="py-2 sm:py-0 sm:pr-4">
              <div class="text-xs text-slate-500">Lo esperable (prob. calibrada del modelo)</div>
              <div class="text-2xl font-bold" :class="today.expected.profit >= 0 ? 'text-green-700' : 'text-red-700'">
                {{ signedMoney(today.expected.profit) }}
              </div>
              <div class="text-xs text-slate-500">quedas en {{ money(today.expected.final) }} ({{ signedPct(today.expected.pct) }})</div>
            </div>
            <div class="py-2 sm:py-0 sm:px-4">
              <div class="text-xs text-slate-500">Si aciertas todas (casi nunca pasa)</div>
              <div class="text-xl font-semibold text-slate-900">+{{ money(today.best.profit) }}</div>
              <div class="text-xs text-slate-500">quedas en {{ money(today.best.final) }} ({{ signedPct(today.best.pct) }})</div>
            </div>
            <div class="py-2 sm:py-0 sm:pl-4">
              <div class="text-xs text-slate-500">Si fallas todas</div>
              <div class="text-xl font-semibold text-slate-900">{{ signedMoney(today.worst.profit) }}</div>
              <div class="text-xs text-slate-500">quedas en {{ money(today.worst.final) }} ({{ signedPct(today.worst.pct) }})</div>
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
                    <th class="py-2 px-3">Valor</th>
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
                    <td class="py-2 px-3 whitespace-nowrap">
                      <span
                        class="inline-block rounded-full px-2 py-0.5 text-xs font-medium"
                        :class="edgeLabel(item.edge / 100).cls"
                        :title="`Edge frente a la cuota: ${signedPct(item.edge)} · modelo solo: ${signedPct(item.modelEdge)}${item.suspicious ? ' (dudoso: más de 20%)' : ''}`"
                      >{{ edgeLabel(item.edge / 100).text }}</span>
                    </td>
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
            "Valor" dice si la apuesta tiene ventaja frente a la cuota de la casa: valor (más de 5%), valor leve
            (2 a 5%) o sin valor. Mezcla la probabilidad del modelo con la de la casa, con el peso que el histórico
            justifica para el modelo; por eso casi todo sale "sin valor". El número exacto aparece al pasar el cursor
            y en el detalle de cada predicción.
          </p>
          <p v-if="today.withoutOdds || today.skippedNoStake" class="text-xs text-slate-500 mt-1">
            <span v-if="today.withoutOdds">{{ today.withoutOdds }} predicciones de hoy quedan fuera por no tener cuota.</span>
            <span v-if="today.skippedNoStake"> {{ today.skippedNoStake }} sin ventaja según Kelly no se apuestan.</span>
          </p>
        </template>

        <!-- Agresivo: todo a una -->
        <details v-if="aggressive" class="mt-3 pt-3 border-t border-slate-100">
          <summary class="text-sm text-slate-700 cursor-pointer">
            🔥 <span class="font-medium">Modo agresivo: todo a una</span>
            <span v-if="aggressive.pick" class="text-slate-500">
              · {{ aggressive.pick.selection }} ({{ aggressive.pick.market }}), cuota {{ aggressive.pick.odds }}, edge
              <span :class="aggressive.pick.edge > 0 ? 'text-green-700' : 'text-red-700'">{{ signedPct(aggressive.pick.edge) }}</span>
            </span>
            <span v-else class="text-slate-500">· hoy no queda ninguna apuesta sin empezar</span>
          </summary>
          <p v-if="!aggressive.pick" class="text-sm text-slate-700 mt-2">
            Hoy no queda ninguna apuesta con cuota en un partido que no haya empezado.
          </p>
          <template v-else>
            <p class="text-sm text-slate-700 mt-2">
              <template v-if="aggressive.note === 'sin_edge_positivo'">
                <strong>Hoy ninguna apuesta tiene edge positivo.</strong> La menos mala sería
              </template>
              <template v-else>La mejor apuesta de hoy ({{ aggressive.positiveEdgeBets }} con edge positivo) es</template>
              <router-link :to="`/predictions/${aggressive.pick.predictionId}`" class="font-semibold underline">
                {{ aggressive.pick.selection }} — {{ aggressive.pick.market }}
              </router-link>
              en {{ aggressive.pick.match }} ({{ aggressive.pick.time }}, {{ aggressive.pick.league }}):
              cuota {{ aggressive.pick.odds }}, probabilidad {{ aggressive.pick.probability }}%,
              edge <span :class="aggressive.pick.edge > 0 ? 'text-green-700' : 'text-red-700'" class="font-semibold">{{ signedPct(aggressive.pick.edge) }}</span>.
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              <div class="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div class="text-xs text-slate-600">Metiendo los {{ money(aggressive.allIn.stake) }} completos hoy</div>
                <div class="text-xl font-bold text-slate-900">
                  {{ money(aggressive.allIn.stake) }} → {{ money(aggressive.allIn.finalIfWin) }}
                  <span class="text-sm font-medium text-slate-600">(x{{ aggressive.allIn.multipleIfWin }})</span>
                </div>
                <div class="text-sm mt-1">
                  <span class="text-green-700 font-semibold">{{ aggressive.allIn.probWin }}% de lograrlo</span> ·
                  <span class="text-red-700 font-semibold">{{ aggressive.allIn.probLoseAll }}% de quedar en ceros</span>
                </div>
              </div>
              <div class="rounded-lg bg-slate-50 border border-slate-200 p-3">
                <div class="text-xs text-slate-600">
                  Para llegar a x{{ aggressive.targetMultiple }}
                  <template v-if="aggressive.chain.steps > 1">reinvirtiendo todo en apuestas como esta</template>
                </div>
                <div class="text-xl font-bold text-slate-900">
                  {{ aggressive.chain.steps }} {{ aggressive.chain.steps === 1 ? 'acierto' : 'aciertos seguidos' }}
                  <span class="text-sm font-medium text-slate-600">
                    (~{{ aggressive.chain.days }} {{ aggressive.chain.days === 1 ? 'día' : 'días' }}, quedas en {{ money(aggressive.chain.finalIfAllWin) }})
                  </span>
                </div>
                <div class="text-sm mt-1">
                  <span class="text-green-700 font-semibold">{{ aggressive.chain.probAllWin }}% de lograrlo</span> ·
                  <span class="text-red-700 font-semibold">{{ aggressive.chain.probLoseAll }}% de quedar en ceros</span>
                </div>
              </div>
            </div>
            <p class="text-xs text-slate-500 mt-3">
              Ignora la estrategia y los topes: es todo o nada. Para esta misma apuesta Kelly recomendaría poner
              {{ aggressive.pick.kellyPct }}% de la caja, no el 100%. Las probabilidades son las del modelo; la cadena
              asume encontrar cada día una apuesta con la misma cuota y probabilidad.
            </p>
          </template>
        </details>
      </div>

      <div v-if="!sim.backtest.bets" v-show="tab === 'historico' || tab === 'auditoria'" class="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500 mb-5">
        No hay apuestas resueltas con cuota guardada para estos filtros.
      </div>

      <template v-else>
        <div v-show="tab === 'historico'" class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-5">
          <!-- Curva -->
          <div class="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-900 mb-1">Evolución de la caja</h2>
            <p class="text-xs text-slate-500 mb-3">
              {{ sim.backtest.bets }} apuestas resueltas entre {{ sim.sample.firstDate }} y {{ sim.sample.lastDate }}
              ({{ sim.backtest.betsPerDay }} por día).
            </p>
            <svg v-if="chart" :viewBox="`0 0 ${chart.w} ${chart.h}`" class="w-full h-48" preserveAspectRatio="none" role="img" aria-label="Curva de la caja">
              <line :x1="0" :x2="chart.w" :y1="chart.baseY" :y2="chart.baseY" stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 4" />
              <polygon :points="chart.area" :fill="chart.positive ? '#f0fdf4' : '#fef2f2'" />
              <polyline :points="chart.line" fill="none" :stroke="chart.positive ? '#16a34a' : '#dc2626'" stroke-width="2" />
            </svg>
            <div class="flex justify-between text-xs text-slate-500 mt-1">
              <span>{{ money(sim.backtest.initial) }} inicial</span>
              <span>{{ money(sim.backtest.final) }} final</span>
            </div>
            <p class="text-xs text-slate-600 mt-3">
              Yield <strong :class="sim.backtest.yield >= 0 ? 'text-green-700' : 'text-red-700'">{{ signedPct(sim.backtest.yield) }}</strong>
              · aciertos <strong>{{ pct(sim.backtest.winRate) }}</strong>
              · caída máxima <strong>{{ pct(sim.backtest.maxDrawdown) }}</strong>
            </p>
          </div>

          <!-- Monte Carlo -->
          <div class="bg-white rounded-xl border border-slate-200 p-4">
            <h2 class="text-lg font-semibold text-slate-900 mb-1">Simulación a futuro</h2>
            <p class="text-xs text-slate-500 mb-3">
              {{ sim.monteCarlo.sims || 0 }} escenarios remuestreando el histórico, horizonte
              {{ sim.monteCarlo.horizonDays || 0 }} días.
            </p>
            <template v-if="sim.monteCarlo.sims">
              <dl class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <dt class="text-slate-600">Prob. de llegar a x{{ sim.params.targetMultiple }}</dt>
                  <dd class="font-semibold text-slate-900">{{ sim.monteCarlo.probReachTarget }}%</dd>
                </div>
                <div class="flex justify-between">
                  <dt class="text-slate-600">Prob. de quebrar la caja</dt>
                  <dd class="font-semibold" :class="sim.monteCarlo.probRuin > 20 ? 'text-red-700' : 'text-slate-900'">
                    {{ sim.monteCarlo.probRuin }}%
                  </dd>
                </div>
                <div class="flex justify-between">
                  <dt class="text-slate-600">Caja mediana al final</dt>
                  <dd class="font-semibold text-slate-900">{{ money(sim.monteCarlo.finalP50) }}</dd>
                </div>
              </dl>
              <details class="mt-3">
                <summary class="text-sm text-blue-700 cursor-pointer">Ver en cuánto tiempo llegan</summary>
                <dl class="space-y-2 text-sm mt-2">
                  <div class="flex justify-between">
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
                </dl>
              </details>
            </template>
            <p v-else class="text-sm text-slate-500">Sin datos suficientes.</p>
          </div>
        </div>

        <!-- Detalle para auditar -->
        <div v-show="tab === 'auditoria'" class="bg-white rounded-xl border border-slate-200 p-4 mb-5">
          <!-- Por mercado -->
          <h3 class="text-base font-semibold text-slate-900 mb-1">Qué mercados pagan</h3>
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
                    <span class="normal-case text-slate-500 font-normal block text-[10px]">vs. cuota de cierre</span>
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
                    <span v-else class="text-xs text-slate-500">sin datos aún</span>
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

          <!-- Consistencia en el tiempo -->
          <h3 class="text-base font-semibold text-slate-900 mt-6 mb-1">¿El edge se sostiene en el tiempo?</h3>
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

          <!-- Muestra -->
          <h3 class="text-base font-semibold text-slate-900 mt-6 mb-1">De dónde sale la muestra</h3>
          <p class="text-xs text-slate-600">
            {{ sim.sample.settledPredictions }} predicciones ya validadas en la ventana;
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
        </div>
      </template>

      <!-- Laboratorio: modelos en prueba contra la casa -->
      <div v-show="tab === 'laboratorio'" class="bg-white rounded-xl border border-slate-200 p-4 mb-5">
        <div class="flex flex-wrap gap-2 mb-3" role="tablist" aria-label="Mercado en prueba">
          <button
            v-for="opt in LAB_OPTIONS"
            :key="opt.key"
            type="button"
            role="tab"
            :aria-selected="labKey === opt.key"
            class="px-3 py-1.5 rounded-lg text-sm font-medium border"
            :class="labKey === opt.key ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'"
            @click="labKey = opt.key"
          >{{ opt.label }}</button>
        </div>
        <h2 class="text-lg font-semibold text-slate-900">{{ labOption.title }}</h2>
        <p class="text-xs text-slate-500 mb-3">
          Un modelo de prueba que suma a la cuota de la casa lo que sabemos de cada jugador (saque, resto, tiebreaks,
          descanso y carga de partidos). No cambia ninguna predicción: solo mide, con cada partido nuevo, si esas
          señales aciertan más que la cuota sola. Cuando lo demuestre, se incorpora al motor.
          {{ labOption.note }}
        </p>
        <p v-if="!lab" class="text-sm text-slate-500">Todavía no hay reporte; se genera con el entrenamiento diario.</p>
        <template v-else>
          <div class="flex flex-wrap items-center gap-3 mb-4">
            <span class="inline-block rounded-full px-3 py-1 text-sm font-medium" :class="labStatus.cls">{{ labStatus.text }}</span>
            <span class="text-sm text-slate-700">{{ labStatus.detail }}</span>
          </div>
          <div class="h-1.5 rounded-full bg-slate-100 overflow-hidden mb-4" role="progressbar" :aria-valuenow="lab.verdict.matches" :aria-valuemax="lab.verdict.needed" aria-label="Partidos nuevos evaluados">
            <div class="h-full rounded-full bg-blue-500" :style="{ width: Math.min(100, (lab.verdict.matches / lab.verdict.needed) * 100) + '%' }"></div>
          </div>
          <div class="overflow-x-auto" tabindex="0">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                  <th class="py-2 pr-4">Prueba</th>
                  <th class="py-2 px-3">Partidos</th>
                  <th class="py-2 px-3">Error de la casa</th>
                  <th class="py-2 px-3">Error del modelo</th>
                  <th class="py-2 px-3">Mejora (IC 95%)</th>
                  <th class="py-2 px-3">Apostando su edge &gt; 3%</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in labRows" :key="row.label" class="border-t border-slate-100">
                  <td class="py-2 pr-4">
                    <span class="font-medium text-slate-900">{{ row.label }}</span>
                    <span class="block text-xs text-slate-500">{{ row.note }}</span>
                  </td>
                  <td class="py-2 px-3 text-slate-600">{{ row.data.matches || 0 }}</td>
                  <template v-if="row.data.matches">
                    <td class="py-2 px-3 text-slate-600">{{ row.data.logLossMarket }}</td>
                    <td class="py-2 px-3 text-slate-600">{{ row.data.logLossModel }}</td>
                    <td class="py-2 px-3 whitespace-nowrap">
                      <span class="font-semibold" :class="row.data.improvement > 0 ? 'text-green-700' : 'text-red-700'">
                        {{ row.data.improvement > 0 ? '+' : '' }}{{ row.data.improvement }}
                      </span>
                      <span class="text-xs text-slate-500">({{ row.data.improvementCiLow }} a {{ row.data.improvementCiHigh }})</span>
                    </td>
                    <td class="py-2 px-3 whitespace-nowrap text-slate-600">
                      <template v-if="row.data.bets">
                        {{ row.data.bets }} apuestas, yield {{ signedPct(row.data.yield) }}
                        <span class="text-xs text-slate-500">({{ signedPct(row.data.yieldCiLow) }} a {{ signedPct(row.data.yieldCiHigh) }})</span>
                      </template>
                      <span v-else class="text-xs text-slate-500">ninguna</span>
                    </td>
                  </template>
                  <td v-else colspan="4" class="py-2 px-3 text-xs text-slate-500">sin partidos todavía</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-xs text-slate-500 mt-3">
            "Error" es el log-loss: más bajo es mejor. La mejora solo cuenta como real cuando todo su intervalo queda
            por encima de cero. El primer vistazo no vale como prueba porque con esos mismos partidos se eligió qué
            señales usar.
          </p>
          <div v-if="lab.weights" class="mt-4">
            <h3 class="text-sm font-semibold text-slate-900 mb-1">Qué señales pesan más hoy</h3>
            <p class="text-xs text-slate-500 mb-2">
              {{ labOption.weightsHelp }}
            </p>
            <ul class="grid grid-cols-1 sm:grid-cols-3 gap-x-6 gap-y-1 text-sm">
              <li v-for="w in lab.weights" :key="w.feature" class="flex justify-between">
                <span class="text-slate-600">{{ w.label }}</span>
                <span class="font-medium" :class="w.weight >= 0 ? 'text-slate-900' : 'text-red-700'">{{ w.weight > 0 ? '+' : '' }}{{ w.weight }}</span>
              </li>
            </ul>
          </div>
        </template>
      </div>

      <!-- Advertencia única -->
      <p class="text-xs text-slate-500 px-1">
        Es un backtest, no una promesa: asume que consigues las mismas cuotas, que el modelo sigue rindiendo igual,
        y no descuenta comisiones ni límites de casa de apuestas.
        <span v-if="!anyRealEdge">Hoy ningún mercado tiene una ventaja demostrada.</span>
        <span v-if="smallSample">
          Con menos de 100 apuestas el resultado es ruido tanto como señal: los días proyectados pueden cambiar mucho
          con unos pocos partidos más.
        </span>
      </p>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useBankrollStore } from '../stores/bankroll.js'
import { edgeLabel } from '../utils/edge.js'

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
  // No edge filter by default: with the market-anchored edge only a handful
  // of bets clear zero, too few to simulate anything.
  minEdge: '',
  days: 365
})

const sim = computed(() => store.simulation)
const today = computed(() => sim.value?.today || null)
const aggressive = computed(() => today.value?.aggressive || null)
const marketCajas = computed(() => sim.value?.marketCajas || [])

// One category on screen at a time; the verdict above stays put.
const tab = ref('mercados')
const tabs = computed(() => [
  { id: 'mercados', label: 'Por mercado' },
  { id: 'hoy', label: 'Hoy', hint: today.value?.bets ? `(${today.value.bets})` : '' },
  { id: 'historico', label: 'Histórico y simulación' },
  { id: 'auditoria', label: 'Auditoría' },
  { id: 'laboratorio', label: 'Laboratorio' }
])

// Shadow model under test against the bookmaker (set1_lab_service).
const LAB_OPTIONS = [
  {
    key: 'set1', label: 'Primer set',
    title: '¿El saque ayuda a ganarle a la casa en el primer set?',
    note: '',
    weightsHelp: 'Positivo: tener más de eso que el rival hace ganar el primer set más veces de lo que la cuota dice.'
  },
  {
    key: 'matchWinner', label: 'Ganador del partido',
    title: '¿Esas mismas señales le ganan a la casa en el ganador del partido?',
    note: 'Un vistazo informal anterior salió en contra; queda en seguimiento para tener la respuesta con datos limpios.',
    weightsHelp: 'Positivo: tener más de eso que el rival hace ganar el partido más veces de lo que la cuota dice.'
  },
  {
    key: 'totalSets', label: 'Total de sets',
    title: '¿Se puede anticipar mejor que la casa si el partido se alarga?',
    note: 'Aquí no importa quién gana sino qué tan parejo es: las señales son la diferencia entre los dos jugadores y la suma de ambos.',
    weightsHelp: 'Positivo: más de eso hace que el partido llegue al set decisivo más veces de lo que la cuota dice.'
  },
  ...[
    ['pointsSet1', 'Puntos · primer set', 'el primer set'],
    ['pointsMatch', 'Puntos · partido', 'el partido'],
    ['pointsTotalSets', 'Puntos · total de sets', 'si el partido se alarga']
  ].map(([key, label, what]) => ({
    key,
    label,
    title: `Modelo de puntos de saque y resto: ¿le gana a la casa en ${what}?`,
    note: 'Este es otro modelo: estima cuántos puntos gana cada jugador al saque contra ese rival (por superficie y dando más peso a lo reciente) y de ahí calcula sets y partido con las reglas del tenis. La prueba mide si acercar la cuota hacia ese modelo acierta más que la cuota sola.',
    weightsHelp: 'Positivo: cuando este modelo ve a un jugador mejor que la cuota, la cuota se queda corta. Cerca de cero o negativo: el modelo no aporta.'
  }))
]
const labKey = ref('set1')
const labOption = computed(() => LAB_OPTIONS.find((o) => o.key === labKey.value))
const lab = computed(() => store.lab?.[labKey.value] || null)
const labRows = computed(() => {
  if (!lab.value) return []
  return [
    {
      label: `Partidos nuevos (después del ${lab.value.frozenAt})`,
      note: 'La prueba que cuenta: nadie los había visto al elegir las señales.',
      data: lab.value.postFreeze || {}
    },
    {
      label: 'Primer vistazo (todo el histórico)',
      note: 'Solo orientativo.',
      data: lab.value.allWalkForward || {}
    }
  ]
})
const labStatus = computed(() => {
  const v = lab.value?.verdict || {}
  const progress = `${v.matches ?? 0} de ${v.needed ?? 0} partidos nuevos evaluados.`
  return (
    {
      juntando_muestra: { text: 'Juntando muestra', cls: 'bg-slate-100 text-slate-700', detail: `${progress} Todavía no se puede concluir nada.` },
      no_demostrado: { text: 'No demostrado', cls: 'bg-amber-100 text-amber-800', detail: `${progress} La mejora no se distingue del azar.` },
      demostrado: { text: 'Demostrado', cls: 'bg-green-100 text-green-800', detail: `${progress} Le gana a la cuota: listo para incorporarse al motor.` },
      descartado: { text: 'Descartado', cls: 'bg-red-100 text-red-800', detail: `${progress} Empeora frente a la cuota.` }
    }[v.level] || { text: '–', cls: 'bg-slate-100 text-slate-600', detail: '' }
  )
})
const smallSample = computed(() => (sim.value?.backtest?.bets || 0) < 100)
const anyRealEdge = computed(() =>
  marketCajas.value.some((r) => r.level === 'edge_real' || r.level === 'ya_alcanzado')
)
// CLV capture (validation_db's new "Capture Closing Odds" node) started 2026-10-02.
const clvSince = '2 de octubre'

const stakeHint = computed(() =>
  form.strategy === 'flat' ? 'sobre el monto inicial' : 'sobre la caja actual'
)

// The advanced settings are folded by default: keep what is applied in sight.
const advancedSummary = computed(() => {
  const stake =
    form.strategy === 'kelly'
      ? `Kelly x${form.kellyMultiplier}`
      : form.strategy === 'flat'
        ? `${form.stakePct}% fijo del monto inicial`
        : `${form.stakePct}% de la caja`
  const edge = { '': 'sin filtro de edge', 0: 'solo edge positivo', 5: 'edge > 5%', 10: 'edge > 10%' }[form.minEdge]
  const span = { 30: '30 días', 90: '90 días', 180: '180 días', 365: '1 año', 1825: 'todo el histórico' }[form.days]
  const parts = [stake, `tope ${form.maxStakePct}%`, edge, span]
  if (form.minConfidence) parts.push(`confianza ≥ ${form.minConfidence}`)
  if (form.sport) parts.push(form.sport === 'tennis' ? 'solo tenis' : 'solo fútbol')
  return parts.join(' · ')
})

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

function isSelected(row) {
  return (sim.value?.params?.market || '') === (row.market || '')
}
function selectMarket(row) {
  form.market = row.market || ''
  run()
}
function levelBadge(level) {
  return (
    {
      edge_real: { text: 'ventaja real', cls: 'bg-green-100 text-green-800' },
      ya_alcanzado: { text: 'ya lo superó', cls: 'bg-green-100 text-green-800' },
      no_concluyente: { text: 'no concluyente', cls: 'bg-amber-100 text-amber-800' },
      pierde: { text: 'pierde', cls: 'bg-red-100 text-red-800' },
      sin_datos: { text: 'sin datos', cls: 'bg-slate-100 text-slate-600' }
    }[level] || { text: '–', cls: 'bg-slate-100 text-slate-600' }
  )
}

const verdict = computed(() => {
  const s = sim.value
  if (!s) return {}
  const p = s.projection
  const target = `x${s.params.targetMultiple}`
  const amount = money(p.targetAmount)
  const good = { accent: 'border-l-green-500', icon: '🚀' }
  const bad = { accent: 'border-l-red-500', icon: '🛑' }
  const warn = { accent: 'border-l-amber-500', icon: '⚠️' }
  const neutral = { accent: 'border-l-slate-300', icon: 'ℹ️' }

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
      detail: `En el histórico, ${money(s.params.initial)} habrían terminado en ${money(s.backtest.final)} (yield ${signedPct(s.backtest.yield)}). Mira en la tabla de abajo qué mercado se comporta mejor por separado.`
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

  if (v.level === 'edge_real' || v.level === 'ya_alcanzado') {
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

onMounted(() => {
  run()
  store.fetchLab()
})
</script>
