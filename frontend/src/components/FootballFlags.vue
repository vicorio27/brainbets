<template>
  <ul v-if="flags && flags.length" class="mt-2 space-y-1" aria-label="Avisos sobre los datos de este partido">
    <li
      v-for="f in flags"
      :key="f.key + f.text"
      class="rounded px-2 py-1 text-xs"
      :class="f.level === 'warn' ? 'bg-amber-50 text-amber-900 ring-1 ring-amber-200' : 'bg-slate-50 text-slate-700 ring-1 ring-slate-200'"
    >
      <span class="font-semibold">{{ f.level === 'warn' ? '⚠ ' : 'ℹ ' }}{{ TITLES[f.key] || 'Aviso' }}.</span> {{ f.text }}
    </li>
  </ul>
</template>

<script setup>
defineProps({ flags: { type: Array, default: () => [] } })

const TITLES = {
  promoted: 'Recién ascendido',
  no_history: 'Sin historial',
  few_matches: 'Pocos partidos',
  extreme_goals: 'Goles esperados raros',
  cup: 'Competición con poca muestra',
  no_price: 'Sin cuota'
}
</script>
