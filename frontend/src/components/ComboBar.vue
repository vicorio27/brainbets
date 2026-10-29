<template>
  <div v-if="combo.count || combo.justSaved" class="fixed inset-x-0 bottom-0 z-40 border-t border-emerald-300 bg-white shadow-[0_-4px_12px_rgba(0,0,0,0.08)]">
    <div v-if="combo.open" class="mx-auto max-h-[70vh] max-w-3xl overflow-y-auto px-4 py-3">
      <ComboPanel />
    </div>
    <button
      class="mx-auto flex w-full max-w-3xl items-center justify-between gap-3 px-4 py-2.5 text-sm"
      :aria-expanded="combo.open"
      @click="toggle"
    >
      <span class="font-semibold text-emerald-800">🧩 Mi combinada ({{ combo.count }})</span>
      <span v-if="!numbers" class="text-slate-700">registrada ✓ <span class="ml-1 text-slate-500">{{ combo.open ? '▼ cerrar' : '▲ ver' }}</span></span>
      <span v-else class="text-slate-700">
        cuota {{ numbers.odds.toFixed(2) }} · salen {{ Math.round(numbers.prob * 100) }}%
        <span class="ml-1 text-slate-500">{{ combo.open ? '▼ cerrar' : '▲ ver' }}</span>
      </span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useComboStore, comboNumbers } from '../stores/combo.js'
import ComboPanel from './ComboPanel.vue'

const combo = useComboStore()
const numbers = computed(() => comboNumbers(combo.legs, combo.amount))
function toggle() {
  combo.open = !combo.open
  if (!combo.open && !combo.count) combo.justSaved = false  // closing after a save hides the bar
}
</script>
