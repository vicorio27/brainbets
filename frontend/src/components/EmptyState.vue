<template>
  <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-8 text-center">
    <div class="text-4xl mb-4">{{ icon }}</div>
    <h3 class="text-lg font-semibold text-slate-900 mb-2">{{ title }}</h3>
    <p class="text-slate-600 mb-4">{{ message }}</p>
    <button
      v-if="showClearButton"
      @click="$emit('clear')"
      class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
    >
      {{ clearButtonText }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  icon: {
    type: String,
    default: '🔍'
  },
  title: {
    type: String,
    required: true
  },
  message: {
    type: String,
    required: true
  },
  showClearButton: {
    type: Boolean,
    default: false
  },
  clearButtonText: {
    type: String,
    default: 'Limpiar filtro'
  }
})

defineEmits(['clear'])
</script>
