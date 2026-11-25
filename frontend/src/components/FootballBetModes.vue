<template>
  <section v-if="modes.singles.length" class="mb-4 rounded-lg border border-slate-200 bg-white">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
      <span class="text-sm font-semibold text-slate-800">Apuestas seguras · fútbol</span>
      <div class="flex gap-1 text-xs" role="tablist">
        <button v-for="t in tabs" :key="t.key" role="tab" :aria-selected="tab === t.key"
          class="rounded px-2 py-1 font-medium"
          :class="tab === t.key ? 'bg-emerald-700 text-white' : 'bg-slate-100 text-slate-700'" @click="tab = t.key">{{ t.label }}</button>
      </div>
    </div>
    <ul v-if="tab === 'single'" class="divide-y divide-slate-100 text-sm">
      <li v-for="s in modes.singles" :key="s.match.matchId" class="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div>
          <div class="font-semibold text-slate-900">{{ s.pick.text }}</div>
          <div class="text-xs text-slate-600">{{ s.match.homeTeam }} vs {{ s.match.awayTeam }} · {{ s.match.league }} · {{ s.match.eventDate }} {{ s.match.eventTime }}</div>
        </div>
        <div class="text-right text-xs text-slate-700">
          <b class="text-sm">{{ pct(s.pick.prob) }}%</b> {{ s.level }} · cuota <b>{{ s.pick.odds.toFixed(2) }}</b>
          · pierde {{ pct(1 - s.pick.prob) }}%
          <div><button class="mt-1 rounded border border-emerald-300 px-2 py-0.5 font-medium text-emerald-800 hover:bg-emerald-50" @click="use([s])">Usar esta</button></div>
        </div>
      </li>
    </ul>
    <ul v-else class="divide-y divide-slate-100 text-sm">
      <li v-if="!modes.combos.length" class="px-3 py-2 text-xs text-slate-600">Hace falta al menos dos partidos con una apuesta segura.</li>
      <li v-for="(c, i) in modes.combos" :key="i" class="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div>
          <div v-for="l in c.legs" :key="l.match.matchId" class="text-slate-900">
            <b>{{ l.pick.text }}</b> <span class="text-xs text-slate-600">{{ l.match.homeTeam }} vs {{ l.match.awayTeam }} · {{ pct(l.pick.prob) }}% · {{ l.pick.odds.toFixed(2) }}</span>
          </div>
        </div>
        <div class="text-right text-xs text-slate-700">
          salen las dos <b class="text-sm">{{ pct(c.prob) }}%</b> · cuota <b>{{ c.odds.toFixed(2) }}</b>
          <div><button class="mt-1 rounded border border-emerald-300 px-2 py-0.5 font-medium text-emerald-800 hover:bg-emerald-50" @click="use(c.legs)">Usar esta</button></div>
        </div>
      </li>
    </ul>
    <p class="border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
      Lo más probable con cuota real de la casa (desde {{ pct(SAFE) }}%), no lo que más paga. La probabilidad es la de la casa sin margen:
      todavía no hay muestra contra la cuota en fútbol, así que es una lista de lo que suele salir, no una señal de valor.
      "Usar esta" la pasa a Mi combinada para registrarla.
    </p>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { conservativeModes, SAFE } from '../utils/footballPicks.js'
import { useFootballComboStore, legKey } from '../stores/combo.js'

const props = defineProps({ matches: { type: Array, required: true }, now: { type: String, required: true } })
const tab = ref('single')
const tabs = [{ key: 'single', label: 'Individual' }, { key: 'combo', label: 'Combinada' }]
const modes = computed(() => conservativeModes(props.matches, props.now))
const pct = (x) => Math.round(x * 100)
const combo = useFootballComboStore()

function use(items) {
  combo.clear()
  for (const { match, pick } of items) {
    const label = `${pick.text} (${match.homeTeam} vs ${match.awayTeam})`
    combo.replace({
      key: legKey(match.matchId, pick.text), matchId: match.matchId, match: `${match.homeTeam} vs ${match.awayTeam}`,
      eventDate: match.eventDate, eventTime: match.eventTime, label, kind: pick.kind, selector: pick.selector,
      probability: pick.prob, odds: pick.odds, oddsKind: 'directa', bestOdds: pick.odds, bestBook: null, bestNeedsCheck: false
    })
  }
  combo.open = true
}
</script>
