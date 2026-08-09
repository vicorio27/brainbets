<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Analytics</h1>

    <div v-if="analyticsStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <div v-else-if="analyticsStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ analyticsStore.error }}
    </div>

    <div v-else-if="analyticsStore.accuracy" class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <KpiCard
        title="Total Predicciones"
        :value="analyticsStore.accuracy.totalPredictions"
        icon="🎯"
      />
      <KpiCard
        title="Acertadas"
        :value="analyticsStore.accuracy.successful"
        color="green"
        icon="✅"
      />
      <KpiCard
        title="Falladas"
        :value="analyticsStore.accuracy.failed"
        color="red"
        icon="❌"
      />
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
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAnalyticsStore } from '../stores/analytics.js'
import KpiCard from '../components/KpiCard.vue'

const analyticsStore = useAnalyticsStore()

function getAccuracyColor(acc) {
  if (!acc) return 'gray'
  if (acc >= 70) return 'green'
  if (acc >= 50) return 'yellow'
  return 'red'
}

onMounted(() => {
  analyticsStore.fetchAccuracy()
})
</script>
