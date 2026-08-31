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
          <label class="text-sm font-medium text-slate-700 flex items-center gap-2 flex-shrink-0">
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

        <div class="overflow-x-auto" tabindex="0">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-slate-500 uppercase tracking-wider">
                <th class="py-2 pr-4">Fecha</th>
                <th class="py-2 px-3">Accuracy</th>
                <th class="py-2 px-3">Validadas</th>
                <th class="py-2 px-3">Aciertos</th>
                <th class="py-2 px-3">🎾 Tenis</th>
                <th class="py-2 px-3">⚽ Fútbol</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in days" :key="d.date" class="border-t border-slate-100">
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
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  <template v-if="d.tennisTotal">{{ d.accuracyTennis }}% <span class="text-xs text-slate-500">({{ d.tennisTotal }})</span></template>
                  <span v-else class="text-xs text-slate-500">–</span>
                </td>
                <td class="py-2 px-3 text-slate-600 whitespace-nowrap">
                  <template v-if="d.footballTotal">{{ d.accuracyFootball }}% <span class="text-xs text-slate-500">({{ d.footballTotal }})</span></template>
                  <span v-else class="text-xs text-slate-500">–</span>
                </td>
              </tr>
            </tbody>
            <tfoot v-if="days.length">
              <tr class="border-t-2 border-slate-200 font-semibold text-slate-900">
                <td class="py-2 pr-4">Total ({{ days.length }} días)</td>
                <td class="py-2 px-3">{{ rangeAccuracy != null ? rangeAccuracy + '%' : '–' }}</td>
                <td class="py-2 px-3">{{ rangeTotal }}</td>
                <td class="py-2 px-3">{{ rangeSuccessful }}</td>
                <td class="py-2 px-3"></td>
                <td class="py-2 px-3"></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <p v-if="!days.length" class="text-sm text-slate-500 text-center py-8">
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

const days = computed(() => analyticsStore.accuracyByDay || [])
const rangeTotal = computed(() => days.value.reduce((n, d) => n + d.total, 0))
const rangeSuccessful = computed(() => days.value.reduce((n, d) => n + d.successful, 0))
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
