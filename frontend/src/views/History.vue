<template>
  <div>
    <h1 class="text-2xl font-bold text-slate-900 mb-6">Historial de Predicciones</h1>

    <div class="mb-4">
      <select v-model="selectedSport" @change="loadHistory" class="border border-slate-300 rounded-lg px-3 py-2 text-sm">
        <option value="">Todos los deportes</option>
        <option value="tennis">Tenis</option>
        <option value="football">Fútbol</option>
      </select>
    </div>

    <div v-if="predictionsStore.loading" class="text-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
    </div>

    <div v-else-if="predictionsStore.error" class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
      {{ predictionsStore.error }}
    </div>

    <div v-else-if="predictionsStore.history.length">
      <PredictionTable :predictions="predictionsStore.history" />
    </div>

    <div v-else class="text-slate-500 text-center py-12">
      No hay historial disponible
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { usePredictionsStore } from '../stores/predictions.js'
import PredictionTable from '../components/PredictionTable.vue'

const predictionsStore = usePredictionsStore()
const selectedSport = ref('')

function loadHistory() {
  predictionsStore.fetchHistory(selectedSport.value || null)
}

onMounted(() => {
  loadHistory()
})
</script>
