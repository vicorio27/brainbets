<template>
  <details class="mt-6 rounded-lg border border-slate-200 bg-white" @toggle="onToggle">
    <summary class="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
      <span class="font-semibold text-slate-800">Simulación del partido</span>
      <span class="text-xs text-slate-600">jugarlo punto por punto, set por set, saque y breaks</span>
    </summary>
    <div class="space-y-3 border-t border-slate-100 px-3 py-3 text-xs text-slate-700">
      <p v-if="loading" class="text-slate-500">Calculando…</p>
      <p v-else-if="error" class="text-amber-800">No se pudo calcular: {{ error }}</p>
      <p v-else-if="sim && !sim.available" class="text-slate-600">{{ sim.reason }}</p>
      <template v-else-if="sim">
        <TennisPlay :names="[sim.player1, sim.player2]" :pa="sim.servePointsWon.p1" :pb="sim.servePointsWon.p2" :best-of="sim.bestOf" />
        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">El partido</h3>
          <p>
            Gana {{ sim.player1 }} {{ pct(sim.matchWin.p1) }}% · gana {{ sim.player2 }} {{ pct(sim.matchWin.p2) }}% (al mejor de {{ sim.bestOf }}).
            Games esperados: <b>{{ sim.expectedGames }}</b> · algún tiebreak {{ pct(sim.tiebreak) }}% · llega al set decisivo {{ pct(sim.decider) }}%.
          </p>
          <p>
            Marcadores más probables (de {{ sim.player1 }}):
            <span v-for="s in sim.setScores.slice(0, 4)" :key="s.score" class="mr-2 whitespace-nowrap"><b>{{ s.score }}</b> ({{ pct(s.p) }}%)</span>
          </p>
        </section>

        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Set por set</h3>
          <div class="overflow-x-auto" tabindex="0">
            <table class="w-full min-w-[24rem] text-left">
              <thead class="text-slate-500">
                <tr>
                  <th class="py-1 pr-2 font-medium">Set</th><th class="px-2 font-medium">Se juega</th><th class="px-2 font-medium">Games</th>
                  <th class="px-2 font-medium">Tiebreak</th><th class="px-2 font-medium">Lo gana {{ sim.player1 }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in sim.sets" :key="s.set" class="border-t border-slate-100">
                  <td class="py-1 pr-2 tabular-nums">{{ s.set }}</td>
                  <td class="px-2 tabular-nums">{{ pct(s.played) }}%</td>
                  <td class="px-2 tabular-nums">{{ s.games ?? '—' }}</td>
                  <td class="px-2 tabular-nums">{{ s.tiebreak == null ? '—' : pct(s.tiebreak) + '%' }}</td>
                  <td class="px-2 tabular-nums">{{ s.p1Wins == null ? '—' : pct(s.p1Wins) + '%' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="mt-1 text-slate-500">Games y tiebreak de cada set cuando se juega. El modelo trata cada set igual (solo cambia quién saca primero), así que lo que cambia de un set a otro es la probabilidad de que se juegue: la del último es la de llegar al set decisivo.</p>
        </section>

        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Saque y breaks</h3>
          <p v-for="[k, name] in [['p1', sim.player1], ['p2', sim.player2]]" :key="k">
            <b>{{ name }}:</b> gana {{ pct(sim.servePointsWon[k]) }}% de sus puntos al saque, sostiene {{ pct(sim.serve[k].hold) }}% de sus juegos de saque
            y hace unos {{ sim.serve[k].breaksExpected }} breaks.
            <span v-if="sim.aces[k]">Promedia {{ sim.aces[k].perMatch }} aces por partido (últimos {{ sim.aces[k].matches }}).</span>
          </p>
          <p class="mt-1 text-slate-500">Fiabilidad del modelo con estos jugadores: {{ pct(sim.trust) }}% (sube con más partidos con estadísticas de saque).</p>
        </section>

        <section v-if="sim.h2h">
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Cara a cara</h3>
          <p>{{ sim.player1 }} {{ sim.h2h.p1Wins }} - {{ sim.h2h.p2Wins }} {{ sim.player2 }} ({{ sim.h2h.total }} partidos guardados).</p>
        </section>
        <p class="rounded bg-amber-50 px-2 py-1 text-amber-900">{{ sim.note }}</p>
      </template>
    </div>
  </details>
</template>

<script setup>
import { ref } from 'vue'
import api from '../stores/api.js'
import TennisPlay from './TennisPlay.vue'

const props = defineProps({ matchId: { type: String, required: true } })
const sim = ref(null)
const loading = ref(false)
const error = ref('')
const pct = (x) => Math.round((x ?? 0) * 100)

async function onToggle(e) {
  if (!e.target.open || sim.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    sim.value = (await api.get(`/matches/${props.matchId}/tennis-simulation`)).data
  } catch (err) {
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}
</script>
