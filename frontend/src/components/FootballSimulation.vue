<template>
  <details class="mt-4 rounded-lg border border-slate-200 bg-white" @toggle="onToggle">
    <summary class="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
      <span class="font-semibold text-slate-800">Simulación del partido</span>
      <span class="text-xs text-slate-600">goles, minutos, córners y H2H</span>
    </summary>
    <div class="space-y-3 border-t border-slate-100 px-3 py-3 text-xs text-slate-700">
      <p v-if="loading" class="text-slate-500">Calculando…</p>
      <p v-else-if="error" class="text-amber-800">No se pudo calcular: {{ error }}</p>
      <template v-else-if="sim">
        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Goles</h3>
          <p>
            Goles esperados: <b>{{ sim.home }} {{ sim.expectedGoals.home }}</b> · <b>{{ sim.away }} {{ sim.expectedGoals.away }}</b>.
            Gana local {{ pct(sim.goals.home) }}% · empate {{ pct(sim.goals.draw) }}% · gana visitante {{ pct(sim.goals.away) }}%.
          </p>
          <p>
            Más de 1.5: {{ pct(sim.goals.over['1.5']) }}% · más de 2.5: {{ pct(sim.goals.over['2.5']) }}% · más de 3.5: {{ pct(sim.goals.over['3.5']) }}% ·
            ambos anotan: {{ pct(sim.goals.btts) }}%.
          </p>
          <p>
            Marcadores más probables:
            <span v-for="s in sim.goals.scorelines" :key="s.score" class="mr-2 whitespace-nowrap"><b>{{ s.score }}</b> ({{ pct(s.p) }}%)</span>
          </p>
        </section>

        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">En qué minutos caen los goles</h3>
          <div class="overflow-x-auto" tabindex="0">
            <table class="w-full min-w-[22rem] text-left">
              <thead class="text-slate-500">
                <tr><th class="py-1 pr-2 font-medium">Tramo</th><th class="px-2 font-medium">{{ sim.home }}</th><th class="px-2 font-medium">{{ sim.away }}</th><th class="px-2 font-medium">Hay gol</th><th class="px-2 font-medium">Liga</th></tr>
              </thead>
              <tbody>
                <tr v-for="(b, i) in sim.minutes.bands" :key="b.band" class="border-t border-slate-100">
                  <td class="py-1 pr-2 tabular-nums">{{ b.band }}'</td>
                  <td class="px-2 tabular-nums">{{ b.home.toFixed(2) }}</td>
                  <td class="px-2 tabular-nums">{{ b.away.toFixed(2) }}</td>
                  <td class="px-2">
                    <span class="inline-block h-2 rounded bg-emerald-500 align-middle" :style="{ width: Math.round(b.anyGoal * 60) + 'px' }"></span>
                    <span class="ml-1 tabular-nums">{{ pct(b.anyGoal) }}%</span>
                  </td>
                  <td class="px-2 tabular-nums text-slate-500">{{ pct(sim.minutes.leagueShape[i]) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="mt-1 text-slate-500">{{ sim.minutes.note }} «Liga» = qué parte de los goles cae en ese tramo en toda la liga.</p>
        </section>

        <section v-if="sim.corners">
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Córners</h3>
          <p>
            Esperados: <b>{{ sim.home }} {{ sim.corners.home }}</b> · <b>{{ sim.away }} {{ sim.corners.away }}</b> · total <b>{{ sim.corners.total }}</b>.
            Más de 8.5: {{ pct(sim.corners.over['8.5']) }}% · 9.5: {{ pct(sim.corners.over['9.5']) }}% · 10.5: {{ pct(sim.corners.over['10.5']) }}% · 11.5: {{ pct(sim.corners.over['11.5']) }}%.
          </p>
        </section>

        <section>
          <h3 class="mb-1 text-sm font-semibold text-slate-800">Enfrentamientos anteriores</h3>
          <p v-if="!sim.h2h.n" class="text-slate-500">No hay enfrentamientos guardados entre los dos.</p>
          <template v-else>
            <p>
              Últimos {{ sim.h2h.n }}: {{ sim.home }} {{ sim.h2h.homeWins }} · empates {{ sim.h2h.draws }} · {{ sim.away }} {{ sim.h2h.awayWins }};
              {{ sim.h2h.avgGoals }} goles por partido<span v-if="sim.h2h.avgCorners">, {{ sim.h2h.avgCorners }} córners</span>.
            </p>
            <ul class="mt-1 space-y-0.5">
              <li v-for="k in sim.h2h.meetings" :key="k.date + k.home">{{ k.date }} · {{ k.home }} <b class="tabular-nums">{{ k.score }}</b> {{ k.away }}</li>
            </ul>
          </template>
          <p class="mt-1 text-slate-500">Se muestra como dato: sumarlo al modelo no mejoró ninguna predicción en las pruebas.</p>
        </section>
        <p class="rounded bg-amber-50 px-2 py-1 text-amber-900">{{ sim.note }}</p>
      </template>
    </div>
  </details>
</template>

<script setup>
import { ref } from 'vue'
import api from '../stores/api.js'

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
    sim.value = (await api.get(`/matches/${props.matchId}/football-simulation`)).data
  } catch (err) {
    error.value = err.response?.data?.detail || err.message
  } finally {
    loading.value = false
  }
}
</script>
