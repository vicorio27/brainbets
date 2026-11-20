<template>
  <div v-if="mine.length || (withRival && theirs.length)" class="mt-1 text-xs space-y-0.5">
    <ul v-if="mine.length" class="space-y-0.5">
      <li v-for="it in mine" :key="'m' + it.key" :class="TONE[it.tone]" :title="it.detail">
        {{ ICON[it.key] || '•' }} {{ it.text }}
      </li>
    </ul>
    <details v-if="withRival && theirs.length" class="text-slate-600">
      <summary class="cursor-pointer">Rival: {{ rivalName }}</summary>
      <ul class="mt-0.5 space-y-0.5 pl-3">
        <li v-for="it in theirs" :key="'t' + it.key" :class="TONE[it.tone]" :title="it.detail">
          {{ ICON[it.key] || '•' }} {{ it.text }}
        </li>
      </ul>
    </details>
  </div>
</template>

<script setup>
import { computed } from 'vue'

// ctx = context[matchId] from /matches/bet-modes: {p1: {player, items}, p2: {...}}
const props = defineProps({
  ctx: { type: Object, default: null },
  side: { type: String, default: null },        // 'p1' | 'p2'
  withRival: { type: Boolean, default: true }
})
const TONE = { good: 'text-emerald-800', bad: 'text-red-700', neutral: 'text-slate-700' }
const ICON = { stakes: '🏆', stakes_news: '🏆', coach: '🧑‍🏫', indoor: '🏟️', top10: '🔟' }
const other = computed(() => (props.side === 'p1' ? 'p2' : 'p1'))
const mine = computed(() => (props.ctx && props.side && props.ctx[props.side]?.items) || [])
const theirs = computed(() => (props.ctx && props.side && props.ctx[other.value]?.items) || [])
const rivalName = computed(() => props.ctx?.[other.value]?.player || '')
</script>
