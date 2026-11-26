<template>
  <div>
    <div class="flex flex-wrap items-baseline justify-between gap-2 mb-2">
      <h1 class="text-2xl font-bold text-slate-900">En vivo</h1>
      <span class="text-xs text-slate-500" title="Una llamada trae todos los partidos en vivo; solo se llama mientras esta página está abierta y algún partido nuestro está en su horario.">
        Llamadas en vivo hoy: {{ calls.today }} de {{ calls.cap }} · se actualiza cada {{ calls.pollSeconds }} s
        <span v-if="updatedAt"> · {{ updatedAt }}</span>
      </span>
    </div>
    <p class="text-xs text-slate-500 mb-4">{{ note }}</p>
    <p v-if="feedError === 'tope_diario'" class="mb-3 text-sm text-amber-800">Se llegó al tope diario de llamadas: se muestra la última lectura.</p>
    <p v-else-if="feedError" class="mb-3 text-sm text-amber-800">El feed en vivo no respondió en la última lectura: se muestra la anterior.</p>

    <p v-if="loading" class="text-sm text-slate-500">Cargando…</p>
    <div v-else-if="!matches.length" class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
      Ahora no se está jugando ningún partido ATP de los nuestros.
      <span v-if="!reading">No se gastan llamadas: el feed se lee solo desde 10 minutos antes de la hora de un partido.</span>
    </div>

    <div v-for="m in matches" :key="m.matchId" class="mb-4 rounded-lg border border-slate-200 bg-white p-4">
      <div class="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div class="text-xs text-slate-500">{{ m.tournament }} · {{ m.date }} {{ m.time }}</div>
          <div class="text-lg font-semibold text-slate-900">{{ m.player1 }} <span class="text-slate-400">vs</span> {{ m.player2 }}</div>
        </div>
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded text-xs font-medium" :class="STATE_CLASS[m.state]">{{ m.state === 'en vivo' ? '🔴 en vivo' : m.state }}</span>
        </div>
      </div>

      <template v-if="m.reading">
        <!-- Score -->
        <div class="mt-3 overflow-x-auto" tabindex="0" role="region" aria-label="Marcador">
          <table class="text-sm">
            <tbody>
              <tr v-for="s in ['p1', 'p2']" :key="s">
                <td class="pr-3 font-medium text-slate-900 whitespace-nowrap">
                  <span v-if="m.reading.server === s" title="Saca">🎾 </span>{{ s === 'p1' ? m.player1 : m.player2 }}
                </td>
                <td v-for="(st, i) in m.reading.sets" :key="i" class="px-2 text-center tabular-nums">{{ s === 'p1' ? st[0] : st[1] }}</td>
                <td v-if="m.reading.game" class="px-2 text-center font-semibold text-emerald-800 tabular-nums">{{ gamePart(m.reading.game, s) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <!-- What just happened -->
          <div>
            <h2 class="text-sm font-semibold text-slate-900 mb-1">Lo último</h2>
            <p v-if="!m.events.length" class="text-sm text-slate-500">Todavía nada: los puntos aparecen desde la segunda lectura.</p>
            <ul v-else class="space-y-1 text-sm">
              <li v-for="(e, i) in m.events.slice(0, 12)" :key="e.at + i" :class="i === 0 ? 'font-medium text-slate-900' : 'text-slate-600'">
                <span class="text-xs text-slate-500 tabular-nums mr-1">{{ hhmm(e.at) }}</span>{{ e.text }}
              </li>
            </ul>
          </div>
          <!-- Overall read -->
          <div>
            <h2 class="text-sm font-semibold text-slate-900 mb-1">En general <span v-if="m.general" class="font-normal text-slate-500">({{ m.general.points }} puntos)</span></h2>
            <ul v-if="m.general" class="space-y-1 text-sm list-disc pl-5 text-slate-700">
              <li v-for="t in m.general.items" :key="t">{{ t }}</li>
            </ul>
          </div>
        </div>

        <!-- Stats side by side -->
        <details class="mt-3 text-sm">
          <summary class="cursor-pointer text-slate-700">Estadísticas del partido</summary>
          <div class="overflow-x-auto mt-1" tabindex="0" role="region" aria-label="Estadísticas">
            <table class="text-sm">
              <thead><tr class="text-xs text-slate-500"><th class="text-left pr-4"></th><th class="px-3">{{ m.player1 }}</th><th class="px-3">{{ m.player2 }}</th></tr></thead>
              <tbody>
                <tr v-for="row in STAT_ROWS" :key="row.key" class="border-t border-slate-100">
                  <td class="pr-4 text-slate-600">{{ row.label }}</td>
                  <td class="px-3 text-center tabular-nums">{{ fmtStat(m.reading.stats.p1[row.key], row) }}</td>
                  <td class="px-3 text-center tabular-nums">{{ fmtStat(m.reading.stats.p2[row.key], row) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>

        <LiveVersus v-if="m.model" :match="m" />
        <p v-else class="mt-3 text-xs text-slate-500">Sin estadísticas de saque suficientes de estos jugadores: no hay simulación contra el marcador real.</p>
      </template>
      <p v-else class="mt-2 text-sm text-slate-500">
        Todavía no aparece en el feed en vivo.
      </p>
    </div>
    <div v-if="upcoming.length" class="mt-2 text-sm text-slate-600">
      <h2 class="font-semibold text-slate-900 mb-1">Faltan hoy</h2>
      <ul class="space-y-0.5">
        <li v-for="u in upcoming" :key="u.matchId"><span class="tabular-nums">{{ u.time }}</span> · {{ u.player1 }} vs {{ u.player2 }}<span v-if="u.tournament" class="text-slate-500"> · {{ u.tournament }}</span></li>
      </ul>
      <p class="text-xs text-slate-500 mt-1">Aparecen arriba solos cuando empiezan (esta página se actualiza cada 30 s).</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import api from '../stores/api.js'
import LiveVersus from '../components/LiveVersus.vue'

const STATE_CLASS = {
  'en vivo': 'bg-red-100 text-red-800',
  'por empezar': 'bg-slate-100 text-slate-700',
  'esperando el feed': 'bg-amber-100 text-amber-900',
  terminado: 'bg-slate-200 text-slate-800'
}
const STAT_ROWS = [
  { key: 'aces', label: 'Aces' },
  { key: 'df', label: 'Dobles faltas' },
  { key: 'winners', label: 'Winners' },
  { key: 'ue', label: 'Errores no forzados' },
  { key: 'first', label: 'Puntos ganados con 1er saque', wt: true },
  { key: 'second', label: 'Puntos ganados con 2º saque', wt: true },
  { key: 'returnPts', label: 'Puntos de resto ganados', wt: true },
  { key: 'net', label: 'Puntos en la red', wt: true },
  { key: 'bpSaved', label: 'Puntos de break salvados', wt: true },
  { key: 'bpConv', label: 'Breaks convertidos', wt: true },
  { key: 'points', label: 'Puntos totales', wt: true },
  { key: 'last10', label: 'Últimas 10 bolas ganadas' }
]

const matches = ref([])
const upcoming = ref([])
const reading = ref(false)
const calls = ref({ today: 0, cap: 0, pollSeconds: 30 })
const note = ref('')
const feedError = ref(null)
const loading = ref(true)
const updatedAt = ref('')
let timer = null

function fmtStat(v, row) {
  if (v == null) return '-'
  if (row.wt) return `${v[0]}/${v[1]}` + (v[1] ? ` (${Math.round((v[0] / v[1]) * 100)}%)` : '')
  return v
}
function gamePart(game, side) {
  const parts = String(game).split('-').map((x) => x.trim())
  return side === 'p1' ? parts[0] : parts[1]
}
function hhmm(iso) {
  return new Date(iso).toLocaleTimeString('es-CO', { timeZone: 'America/Bogota', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
async function load() {
  try {
    // no client cache here: each read must reach the backend, which caches the feed itself
    const { data } = await api.get('/live/matches', { params: { t: Date.now() } })
    matches.value = data.matches
    upcoming.value = data.upcoming || []
    reading.value = data.reading
    calls.value = data.calls
    note.value = data.note
    feedError.value = data.feedError
    updatedAt.value = 'leído ' + hhmm(new Date().toISOString())
  } catch (e) {
    feedError.value = 'sin_conexion'
  } finally {
    loading.value = false
  }
}
onMounted(() => {
  load()
  timer = setInterval(load, (calls.value.pollSeconds || 30) * 1000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
