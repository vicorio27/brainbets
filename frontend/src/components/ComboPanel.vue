<template>
  <div class="text-sm text-slate-700">
    <div class="flex items-center justify-between gap-2">
      <h2 class="text-base font-semibold text-slate-900">🧩 Mi combinada</h2>
      <button v-if="combo.legs.length" class="text-xs text-slate-600 underline hover:text-slate-900" @click="combo.clear()">vaciar</button>
    </div>

    <p v-if="combo.justSaved && !combo.legs.length" class="mt-2 text-green-700">
      Registrada. Se liquida sola cuando terminen los partidos:
      <router-link to="/mis-apuestas" class="font-semibold underline">ver Mis apuestas</router-link>
    </p>
    <p v-if="!combo.legs.length" class="mt-2 text-slate-600">
      Agrega apuestas con el botón <span class="font-semibold">+</span> en «Lo más probable» de cada partido (pestaña Hoy).
      Una por partido.
    </p>

    <template v-else>
      <ul class="mt-2 divide-y divide-slate-100">
        <li v-for="l in combo.legs" :key="l.key" class="py-2 flex items-start gap-2">
          <span class="w-9 shrink-0 font-semibold text-slate-900">{{ pct(l.probability) }}</span>
          <div class="min-w-0 flex-1">
            <div>{{ l.label }}</div>
            <div class="text-xs text-slate-500">{{ l.match }} · {{ l.eventTime || '' }}</div>
            <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <label class="flex items-center gap-1">
                tu cuota
                <input
                  type="number" step="0.01" min="1.01" :value="l.myOdds"
                  :aria-label="`Cuota de ${l.label}`"
                  class="w-20 rounded border border-slate-300 px-1.5 py-0.5"
                  @change="combo.setOdds(l.key, $event.target.value)"
                >
              </label>
              <span v-if="l.bestBook" class="text-slate-600">
                mejor: {{ l.bestOdds.toFixed(2) }} en {{ bookName(l.bestBook) }}<template v-if="l.bestNeedsCheck"> <span class="text-amber-700">(muy por encima de las demás: confírmala)</span></template>
              </span>
              <span v-else-if="l.oddsKind === 'aprox'" class="text-amber-700">cuota estimada: confírmala en la casa</span>
              <span v-if="started(l)" class="font-medium text-red-700">ya empezó</span>
              <span :class="numbers.singles.find(s => s.key === l.key).expectedPct >= 0 ? 'text-green-700' : 'text-slate-500'">
                sola: {{ signedPct(numbers.singles.find(s => s.key === l.key).expectedPct) }} en promedio
              </span>
            </div>
          </div>
          <button class="shrink-0 px-1 text-slate-500 hover:text-red-700" :aria-label="`Quitar ${l.label}`" @click="combo.remove(l.key)">✕</button>
        </li>
      </ul>

      <label class="mt-2 flex items-center gap-2">
        Monto (COP)
        <input
          type="number" min="1000" step="1000" :value="combo.amount" aria-label="Monto a apostar"
          class="w-36 rounded border border-slate-300 px-2 py-1"
          @change="combo.setAmount($event.target.value)"
        >
      </label>

      <div class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
        <div>Salen {{ combo.legs.length === 1 ? 'esta' : (combo.legs.length === 2 ? 'las dos' : `las ${combo.legs.length}`) }}:
          <span class="font-semibold text-slate-900">{{ pct(numbers.prob) }}</span></div>
        <div>Cuota total: <span class="font-semibold text-slate-900">{{ numbers.odds.toFixed(2) }}</span>
          <span v-if="numbers.bestOdds > numbers.odds + 0.005" class="text-slate-500"> (con las mejores: {{ numbers.bestOdds.toFixed(2) }})</span></div>
        <div>Si ganas: <span class="font-semibold text-green-700">+{{ cop(numbers.win) }}</span></div>
        <div>Si pierdes: <span class="font-semibold text-red-700">−{{ cop(numbers.lose) }}</span></div>
        <div class="col-span-2">Resultado promedio:
          <span class="font-semibold" :class="numbers.expected >= 0 ? 'text-green-700' : 'text-red-700'">{{ numbers.expected >= 0 ? '+' : '−' }}{{ cop(Math.abs(numbers.expected)) }} ({{ signedPct(numbers.expectedPct) }})</span>
        </div>
        <div class="col-span-2 text-slate-600">Si la repites 10 veces, sale las 10 el {{ pct(numbers.allTen) }} de las veces.</div>
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          class="rounded-lg bg-emerald-700 px-3 py-1.5 font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
          :disabled="saving || !canRegister"
          @click="register"
        >{{ saving ? 'Registrando…' : `Registrar ${combo.legs.length === 1 ? 'apuesta sola' : 'combinada'} por $${cop(combo.amount)}` }}</button>
        <span class="text-xs text-slate-500">Regístrala cuando ya la hayas hecho en la casa, con la cuota que te dieron.</span>
      </div>
      <p v-if="!canRegister" class="mt-1 text-xs text-amber-700">{{ blockReason }}</p>
      <p v-if="saveError" class="mt-1 text-xs text-red-700">{{ saveError }}</p>

      <p class="mt-2 text-xs text-slate-500">
        Las probabilidades son las de la casa sin su margen. En una combinada pagas ese margen una vez por cada apuesta,
        así que en promedio pierde más que la peor de sus apuestas sola.
      </p>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useComboStore, comboNumbers } from '../stores/combo.js'
import { useMyBetsStore } from '../stores/mybets.js'

const combo = useComboStore()
const myBets = useMyBetsStore()
const numbers = computed(() => comboNumbers(combo.legs, combo.amount))

const saving = ref(false)
const saveError = ref(null)
const blockReason = computed(() => {
  if (combo.legs.some((l) => !l.selector)) return 'Hay selecciones agregadas antes de esta versión: quítalas y vuelve a agregarlas desde su partido.'
  if (combo.legs.some(started)) return 'Quita los partidos que ya empezaron: solo se registran apuestas antes del inicio.'
  return ''
})
const canRegister = computed(() => combo.legs.length > 0 && !blockReason.value)
async function register() {
  saving.value = true
  saveError.value = null
  try {
    await myBets.register(combo.amount, combo.legs)
    combo.clear()
    combo.justSaved = true
  } catch (err) {
    saveError.value = err.response?.data?.detail || err.message
  } finally {
    saving.value = false
  }
}

const BOOKS = { Pncl: 'Pinnacle' }
const bookName = (b) => BOOKS[b] || b
const pct = (p) => `${Math.round(p * 100)}%`
const signedPct = (x) => `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(1)}%`
const cop = (v) => new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 }).format(Math.round(v))

function nowBogota() {
  const d = new Date()
  return {
    date: d.toLocaleDateString('en-CA', { timeZone: 'America/Bogota' }),
    time: d.toLocaleTimeString('en-GB', { timeZone: 'America/Bogota', hour: '2-digit', minute: '2-digit' })
  }
}
function started(l) {
  if (!l.eventDate) return false
  const n = nowBogota()
  return l.eventDate < n.date || (l.eventDate === n.date && !!l.eventTime && l.eventTime <= n.time)
}
</script>
