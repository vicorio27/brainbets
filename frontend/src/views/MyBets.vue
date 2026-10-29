<template>
  <div>
    <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">Mis apuestas</h1>
        <p class="text-sm text-slate-600">
          Las que registraste desde la calculadora (botón + en «Lo más probable»). Se liquidan solas con el resultado,
          cada hora junto a la validación o al abrir esta página.
        </p>
      </div>
      <button
        class="self-start rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:self-auto"
        :disabled="store.loading" @click="store.fetch()"
      >{{ store.loading ? 'Actualizando…' : 'Actualizar' }}</button>
    </div>

    <p v-if="store.error" class="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{{ store.error }}</p>

    <div v-if="summary" class="mb-6 grid gap-3 md:grid-cols-3">
      <div v-for="g in groups" :key="g.key" class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div class="text-sm font-semibold text-slate-900">{{ g.title }}</div>
        <template v-if="summary[g.key].bets">
          <div class="mt-1 text-2xl font-bold" :class="summary[g.key].profit >= 0 ? 'text-green-700' : 'text-red-700'">
            {{ signedCop(summary[g.key].profit) }}
          </div>
          <div class="text-xs text-slate-500">ganancia neta de las ya liquidadas</div>
          <dl class="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-sm text-slate-700">
            <dt>Apuestas</dt><dd class="text-right">{{ summary[g.key].bets }}</dd>
            <dt>Ganadas / perdidas</dt><dd class="text-right">{{ summary[g.key].won }} / {{ summary[g.key].lost }}</dd>
            <dt>Pendientes</dt><dd class="text-right">{{ summary[g.key].pending }}<template v-if="summary[g.key].pendingStaked"> (${{ cop(summary[g.key].pendingStaked) }})</template></dd>
            <template v-if="summary[g.key].void"><dt>Anuladas</dt><dd class="text-right">{{ summary[g.key].void }}</dd></template>
            <dt>Apostado (liquidadas)</dt><dd class="text-right">${{ cop(summary[g.key].staked) }}</dd>
            <dt>Rendimiento</dt>
            <dd class="text-right" :class="(summary[g.key].yield ?? 0) >= 0 ? 'text-green-700' : 'text-red-700'">{{ summary[g.key].yield == null ? '—' : signedPct(summary[g.key].yield) }}</dd>
            <dt>Acierto</dt>
            <dd class="text-right" :title="'La casa (sin su margen) les daba en promedio ' + pct(summary[g.key].expectedWinRate)">
              {{ pct(summary[g.key].winRate) }}<span class="text-slate-500"> (esperado {{ pct(summary[g.key].expectedWinRate) }})</span>
            </dd>
          </dl>
        </template>
        <p v-else class="mt-1 text-sm text-slate-500">Todavía ninguna.</p>
      </div>
    </div>

    <div class="mb-3 inline-flex overflow-hidden rounded-lg border border-slate-300 text-sm">
      <button
        v-for="f in filters" :key="f.key"
        class="px-3 py-1.5" :class="filter === f.key ? 'bg-emerald-700 text-white' : 'bg-white text-slate-700 hover:bg-slate-50'"
        @click="filter = f.key"
      >{{ f.label }} ({{ countOf(f.key) }})</button>
    </div>

    <div v-if="store.data && !shown.length" class="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
      <template v-if="!store.data.bets.length">
        Aún no registras apuestas. Arma una en el Dashboard con el botón <span class="font-semibold">+</span> de «Lo más probable»
        y toca «Registrar» en Mi combinada.
      </template>
      <template v-else>No hay apuestas en este filtro.</template>
    </div>

    <ul class="space-y-3">
      <li v-for="b in shown" :key="b.id" class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2 text-sm">
            <span class="rounded-full px-2 py-0.5 text-xs font-semibold" :class="STATUS[b.status].cls">{{ STATUS[b.status].label }}</span>
            <span class="font-medium text-slate-900">{{ b.type === 'sola' ? 'Sola' : `Combinada de ${b.legs.length}` }}</span>
            <span class="text-slate-500">{{ when(b.createdAt) }}</span>
          </div>
          <div class="text-right text-sm">
            <span class="text-slate-600">${{ cop(b.amount) }} a {{ b.odds.toFixed(2) }}</span>
            <span v-if="b.profit != null" class="ml-2 font-semibold" :class="b.profit >= 0 ? 'text-green-700' : 'text-red-700'">{{ signedCop(b.profit) }}</span>
            <span v-else class="ml-2 text-slate-500">si gana: +${{ cop(b.amount * (b.odds - 1)) }}</span>
          </div>
        </div>
        <ul class="mt-2 space-y-1 text-sm">
          <li v-for="(l, i) in b.legs" :key="i" class="flex items-baseline gap-2">
            <span class="w-5 shrink-0 text-center" :title="STATUS[l.status].label">{{ STATUS[l.status].icon }}</span>
            <span class="min-w-0 flex-1">
              {{ l.label }} <span class="text-slate-500">· {{ l.odds.toFixed(2) }}</span>
              <span class="block text-xs text-slate-500">{{ l.match }}<template v-if="l.matchDate"> · {{ when(l.matchDate) }}</template><template v-if="l.probability != null"> · la casa le daba {{ pct(l.probability) }}</template></span>
            </span>
          </li>
        </ul>
        <div class="mt-2 flex items-center justify-between text-xs text-slate-500">
          <span v-if="b.probability != null">Salían {{ b.legs.length === 1 ? '' : 'todas ' }}el {{ pct(b.probability) }} de las veces</span>
          <span v-else></span>
          <button v-if="b.status === 'PENDING'" class="text-red-700 underline" @click="remove(b)">borrar (registrada por error)</button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useMyBetsStore } from '../stores/mybets.js'

const store = useMyBetsStore()
const filter = ref('all')
const groups = [
  { key: 'all', title: 'Todas' },
  { key: 'sola', title: 'Solas' },
  { key: 'combinada', title: 'Combinadas' }
]
const filters = [
  { key: 'all', label: 'Todas' },
  { key: 'PENDING', label: 'Pendientes' },
  { key: 'WON', label: 'Ganadas' },
  { key: 'LOST', label: 'Perdidas' }
]
const STATUS = {
  PENDING: { label: 'Pendiente', icon: '⏳', cls: 'bg-slate-100 text-slate-700' },
  WON: { label: 'Ganada', icon: '✅', cls: 'bg-green-100 text-green-800' },
  LOST: { label: 'Perdida', icon: '❌', cls: 'bg-red-100 text-red-800' },
  VOID: { label: 'Anulada', icon: '➖', cls: 'bg-amber-100 text-amber-800' }
}

const summary = computed(() => store.data?.summary)
const bets = computed(() => store.data?.bets || [])
const shown = computed(() => (filter.value === 'all' ? bets.value : bets.value.filter((b) => b.status === filter.value)))
const countOf = (key) => (key === 'all' ? bets.value.length : bets.value.filter((b) => b.status === key).length)

const cop = (v) => new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 }).format(Math.round(v))
const signedCop = (v) => `${v >= 0 ? '+' : '−'}$${cop(Math.abs(v))}`
const pct = (p) => (p == null ? '—' : `${Math.round(p * 100)}%`)
const signedPct = (x) => `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(1)}%`
const when = (iso) => new Date(iso).toLocaleString('es-CO', {
  timeZone: 'America/Bogota', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
})

async function remove(b) {
  if (!window.confirm(`¿Borrar esta apuesta de $${cop(b.amount)}? Solo si la registraste por error.`)) return
  try {
    await store.remove(b.id)
  } catch (err) {
    store.error = err.response?.data?.detail || err.message
  }
}

onMounted(() => store.fetch())
</script>
