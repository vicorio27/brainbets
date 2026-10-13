<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Analytics</h1>

    <div v-if="analyticsStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <div v-else-if="analyticsStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ analyticsStore.error }}
    </div>

    <template v-else>
      <div v-if="analyticsStore.accuracy" class="grid grid-cols-1 md:grid-cols-3 gap-6">
        <KpiCard title="Total Predicciones" :value="analyticsStore.accuracy.totalPredictions" icon="🎯" />
        <KpiCard title="Acertadas" :value="analyticsStore.accuracy.successful" color="green" icon="✅" />
        <KpiCard title="Falladas" :value="analyticsStore.accuracy.failed" color="red" icon="❌" />
        <KpiCard
          title="Accuracy Global"
          :value="analyticsStore.accuracy.accuracy + '%'"
          :color="getAccuracyColor(analyticsStore.accuracy.accuracy)"
          icon="📊"
        />
        <KpiCard
          title="Accuracy Tenis"
          :value="analyticsStore.accuracy.accuracyTennis + '%'"
          :color="getAccuracyColor(analyticsStore.accuracy.accuracyTennis)"
          icon="🎾"
        />
        <KpiCard
          title="Accuracy Fútbol"
          :value="analyticsStore.accuracy.accuracyFootball + '%'"
          :color="getAccuracyColor(analyticsStore.accuracy.accuracyFootball)"
          icon="⚽"
        />
      </div>

      <!-- Accuracy por día -->
      <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-4 mt-6">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
          <div>
            <h2 class="text-lg font-semibold text-slate-900">Accuracy por día</h2>
            <p class="text-xs text-slate-500">
              Predicciones validadas, agrupadas por el día del partido (hora Bogotá).
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-3 flex-shrink-0">
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2">
            Mercado:
            <select
              v-model="marketFilter"
              aria-label="Mercado"
              class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Todos</option>
              <option v-for="m in marketOptions" :key="m.key" :value="m.key">{{ marketLabel(m) }}</option>
            </select>
          </label>
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2">
            Rango:
            <select
              v-model.number="rangeDays"
              aria-label="Rango de días"
              class="px-2 py-1.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option :value="14">14 días</option>
              <option :value="30">30 días</option>
              <option :value="60">60 días</option>
              <option :value="120">120 días</option>
            </select>
          </label>
          </div>
        </div>

        <p v-if="!marketFilter && bestCounts.length" class="text-xs text-slate-600 mb-3">
          <span class="font-medium text-slate-700">Días como el mercado más acertado:</span>
          <button
            v-for="b in bestCounts"
            :key="b.key"
            type="button"
            class="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700"
            :title="'Ver solo ' + b.market"
            @click="marketFilter = b.key"
          >
            {{ marketLabel(b) }} <span class="font-semibold">{{ b.days }}</span>
          </button>
          <span class="block mt-1 text-slate-500">
            Cuenta solo mercados con al menos {{ minSample }} predicciones validadas ese día. Toca una fila para ver todos los mercados del día.
          </span>
        </p>

        <div class="overflow-x-auto" tabindex="0">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-4">Fecha</th>
                <th class="py-2 px-3">Accuracy</th>
                <th class="py-2 px-3">Validadas</th>
                <th class="py-2 px-3">Aciertos</th>
                <template v-if="!marketFilter">
                  <th class="py-2 px-3">Mercado más acertado</th>
                  <th class="py-2 px-3">🎾 Tenis</th>
                  <th v-if="hasFootball" class="py-2 px-3">⚽ Fútbol</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <template v-for="d in rows" :key="d.date">
              <tr
                class="border-t border-slate-100"
                :class="!marketFilter ? 'cursor-pointer hover:bg-slate-50' : ''"
                @click="toggleDay(d.date)"
              >
                <td class="py-2 pr-4 font-medium text-slate-900 whitespace-nowrap">{{ formatDay(d.date) }}</td>
                <td class="py-2 px-3 whitespace-nowrap">
                  <div class="flex items-center gap-2">
                    <div class="w-20 sm:w-28 bg-slate-200 rounded-full h-2 flex-shrink-0">
                      <div class="h-2 rounded-full" :class="barColor(d.accuracy)" :style="{ width: (d.accuracy || 0) + '%' }"></div>
                    </div>
                    <span class="font-semibold" :class="textColor(d.accuracy)">{{ d.accuracy != null ? d.accuracy + '%' : '–' }}</span>
                  </div>
                </td>
                <td class="py-2 px-3 text-slate-600">{{ d.total }}</td>
                <td class="py-2 px-3 text-slate-600">{{ d.successful }}</td>
                <template v-if="!marketFilter">
                <td class="py-2 px-3 whitespace-nowrap">
                  <template v-if="d.bestMarket">
                    <span class="font-medium text-slate-900">{{ marketLabel(d.bestMarket) }}</span>
                    <span class="ml-1" :class="textColor(d.bestMarket.accuracy)">{{ d.bestMarket.accuracy }}%</span>
                    <span class="text-xs text-slate-500"> ({{ d.bestMarket.successful }}/{{ d.bestMarket.total }})</span>
                  </template>
                  <span v-else class="text-xs text-slate-500">muestra insuficiente</span>
                </td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  <template v-if="d.tennisTotal">{{ d.accuracyTennis }}% <span class="text-xs text-slate-500">({{ d.tennisTotal }})</span></template>
                  <span v-else class="text-xs text-slate-500">–</span>
                </td>
                <td v-if="hasFootball" class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  <template v-if="d.footballTotal">{{ d.accuracyFootball }}% <span class="text-xs text-slate-500">({{ d.footballTotal }})</span></template>
                  <span v-else class="text-xs text-slate-500">–</span>
                </td>
                </template>
              </tr>
              <tr v-if="!marketFilter && openDay === d.date" class="bg-slate-50">
                <td colspan="7" class="py-2 px-3">
                  <div class="flex flex-wrap gap-2">
                    <span
                      v-for="m in d.markets"
                      :key="m.sport + '|' + m.market"
                      class="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 bg-white text-xs text-slate-700"
                    >
                      {{ marketLabel(m) }}
                      <span class="font-semibold" :class="textColor(m.accuracy)">{{ m.accuracy }}%</span>
                      <span class="text-slate-500">({{ m.successful }}/{{ m.total }})</span>
                    </span>
                  </div>
                </td>
              </tr>
              </template>
            </tbody>
            <tfoot v-if="rows.length">
              <tr class="border-t-2 border-slate-200 font-semibold text-slate-900">
                <td class="py-2 pr-4">Total ({{ rows.length }} días)</td>
                <td class="py-2 px-3">{{ rangeAccuracy != null ? rangeAccuracy + '%' : '–' }}</td>
                <td class="py-2 px-3">{{ rangeTotal }}</td>
                <td class="py-2 px-3">{{ rangeSuccessful }}</td>
                <td v-if="!marketFilter" colspan="3" class="py-2 px-3"></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <p v-if="!rows.length" class="text-sm text-slate-500 text-center py-8">
          No hay predicciones validadas en este rango.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useAnalyticsStore } from '../stores/analytics.js'
import KpiCard from '../components/KpiCard.vue'

const analyticsStore = useAnalyticsStore()
const rangeDays = ref(60)

const marketFilter = ref('')
const openDay = ref(null)

const days = computed(() => analyticsStore.accuracyByDay || [])
const minSample = computed(() => analyticsStore.bestMarketMinSample)
// The football column only shows when the range has football in it.
const hasFootball = computed(() => days.value.some((d) => d.footballTotal))
const marketKey = (m) => m.sport + '|' + m.market

const marketOptions = computed(() => {
  const seen = new Map()
  for (const d of days.value) {
    for (const m of d.markets || []) {
      const key = marketKey(m)
      const o = seen.get(key) || { key, market: m.market, sport: m.sport, total: 0 }
      o.total += m.total
      seen.set(key, o)
    }
  }
  return [...seen.values()].sort((a, b) => b.total - a.total)
})

// With a market selected, each day shows that market's own numbers.
const rows = computed(() => {
  if (!marketFilter.value) return days.value
  return days.value
    .map((d) => {
      const m = (d.markets || []).find((x) => marketKey(x) === marketFilter.value)
      return m ? { date: d.date, total: m.total, successful: m.successful, accuracy: m.accuracy } : null
    })
    .filter(Boolean)
})

const bestCounts = computed(() => {
  const counts = new Map()
  for (const d of days.value) {
    if (!d.bestMarket) continue
    const key = marketKey(d.bestMarket)
    const o = counts.get(key) || { key, market: d.bestMarket.market, sport: d.bestMarket.sport, days: 0 }
    o.days += 1
    counts.set(key, o)
  }
  return [...counts.values()].sort((a, b) => b.days - a.days)
})

const rangeTotal = computed(() => rows.value.reduce((n, d) => n + d.total, 0))
const rangeSuccessful = computed(() => rows.value.reduce((n, d) => n + d.successful, 0))
const rangeAccuracy = computed(() =>
  rangeTotal.value ? Math.round((rangeSuccessful.value / rangeTotal.value) * 1000) / 10 : null
)

function getAccuracyColor(acc) {
  if (!acc) return 'gray'
  if (acc >= 70) return 'green'
  if (acc >= 50) return 'yellow'
  return 'red'
}
function barColor(acc) {
  if (acc == null) return 'bg-slate-300'
  if (acc >= 60) return 'bg-green-600'
  if (acc >= 45) return 'bg-amber-500'
  return 'bg-red-500'
}
function textColor(acc) {
  if (acc == null) return 'text-slate-400'
  if (acc >= 60) return 'text-green-700'
  if (acc >= 45) return 'text-amber-700'
  return 'text-red-700'
}
function marketLabel(m) {
  return (m.sport === 'football' ? '⚽ ' : '🎾 ') + m.market
}
function toggleDay(date) {
  if (marketFilter.value) return
  openDay.value = openDay.value === date ? null : date
}
function formatDay(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('es-ES', { weekday: 'short', day: '2-digit', month: 'short' })
}

watch(rangeDays, (n) => analyticsStore.fetchAccuracyByDay(n))

onMounted(() => {
  analyticsStore.fetchAccuracy()
  analyticsStore.fetchAccuracyByDay(rangeDays.value)
})
</script>
