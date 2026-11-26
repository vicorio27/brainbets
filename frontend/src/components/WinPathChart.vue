<template>
  <figure class="m-0">
    <svg :viewBox="`0 0 ${W} ${H}`" class="block w-full" role="img" :aria-label="label">
      <defs>
        <clipPath :id="`${uid}-top`"><rect x="0" y="0" :width="W" :height="mid" /></clipPath>
        <clipPath :id="`${uid}-bot`"><rect x="0" :y="mid" :width="W" :height="H - mid" /></clipPath>
        <linearGradient :id="`${uid}-a`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" :stop-color="C1" stop-opacity="0.75" /><stop offset="1" :stop-color="C1" stop-opacity="0.08" />
        </linearGradient>
        <linearGradient :id="`${uid}-b`" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" :stop-color="C2" stop-opacity="0.75" /><stop offset="1" :stop-color="C2" stop-opacity="0.08" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" :width="W" :height="mid" :fill="C1" fill-opacity="0.06" />
      <rect x="0" :y="mid" :width="W" :height="H - mid" :fill="C2" fill-opacity="0.06" />
      <line :x1="PADL" :x2="W - PAD" :y1="mid" :y2="mid" stroke="#94a3b8" stroke-dasharray="5 5" />
      <text :x="PADL" y="12" class="fill-slate-500" font-size="12">{{ names[0] }} gana</text>
      <text :x="PADL" :y="H - 6" class="fill-slate-500" font-size="12">{{ names[1] }} gana</text>
      <text :x="PADL - 6" :y="TOP + 4" text-anchor="end" class="fill-slate-500" font-size="11">100%</text>
      <text :x="PADL - 6" :y="mid + 4" text-anchor="end" class="fill-slate-500" font-size="11">50%</text>
      <text :x="PADL - 6" :y="H - BOT + 4" text-anchor="end" class="fill-slate-500" font-size="11">0%</text>

      <g v-for="b in bounds" :key="b.i">
        <line :x1="b.x" :x2="b.x" y1="16" :y2="H - 18" stroke="#94a3b8" stroke-dasharray="2 4" />
        <text :x="b.x + 4" :y="H - 6" style="paint-order: stroke" stroke="#fff" stroke-width="3" class="fill-slate-500" font-size="11">fin del set {{ b.set }}</text>
      </g>

      <path :d="area" :fill="`url(#${uid}-a)`" :clip-path="`url(#${uid}-top)`" />
      <path :d="area" :fill="`url(#${uid}-b)`" :clip-path="`url(#${uid}-bot)`" />
      <polyline :points="line" fill="none" stroke="#334155" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />

      <g v-for="b in breaks" :key="'k' + b.i">
        <rect :x="b.x - 5" :y="b.y - 5" width="10" height="10" transform-origin="center" :transform="`rotate(45 ${b.x} ${b.y})`"
          :fill="b.w === 0 ? C1 : C2" stroke="#fff" stroke-width="1.5" />
        <title>Break de {{ names[b.w] }}</title>
      </g>

      <circle v-if="last" :cx="last.x" :cy="last.y" r="9" :fill="last.p >= 0.5 ? C1 : C2" fill-opacity="0.35" class="wp-pulse" />
      <circle v-if="last" :cx="last.x" :cy="last.y" r="5" :fill="last.p >= 0.5 ? C1 : C2" stroke="#fff" stroke-width="2" />
    </svg>
    <figcaption class="mt-1 text-xs text-slate-500">
      Cada punto de la línea es la probabilidad de ganar el partido al terminar un game (de verdad jugado).
      El rombo marca un break. Se reconstruye con el punto a punto del feed.
    </figcaption>
  </figure>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  path: { type: Array, required: true }, // [{p, event, w, set}] first item = before the match
  now: { type: Number, default: null }, // probability right now (mid-game), appended as the last point
  names: { type: Array, required: true }
})
const W = 800
const H = 200
const PAD = 14
const PADL = 40
const TOP = 20
const BOT = 22
const C1 = '#f59e0b'
const C2 = '#ec4899'
const uid = `wp${Math.random().toString(36).slice(2, 8)}`
const mid = TOP + (H - TOP - BOT) / 2

const pts = computed(() => {
  const base = props.path.map((x) => ({ ...x }))
  const lastEv = base.length ? base[base.length - 1].event : ''
  if (props.now != null && lastEv !== 'match') base.push({ p: props.now, event: 'now' })
  const n = Math.max(1, base.length - 1)
  return base.map((x, i) => ({
    ...x, i, x: PADL + (i * (W - PADL - PAD)) / n, y: TOP + (1 - x.p) * (H - TOP - BOT)
  }))
})
const line = computed(() => pts.value.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(' '))
const area = computed(() => {
  if (!pts.value.length) return ''
  const f = pts.value[0]
  const l = pts.value[pts.value.length - 1]
  return `M${f.x},${mid} ` + pts.value.map((q) => `L${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(' ') + ` L${l.x},${mid} Z`
})
const bounds = computed(() => pts.value.filter((q) => q.event === 'set').map((q) => ({ i: q.i, x: q.x, set: q.set })))
const breaks = computed(() => pts.value.filter((q) => q.event === 'break'))
const last = computed(() => pts.value[pts.value.length - 1] || null)
const label = computed(() => {
  if (!pts.value.length) return 'Sin datos'
  const pct = (x) => Math.round(x * 100)
  return `Probabilidad de que gane ${props.names[0]}: al empezar ${pct(pts.value[0].p)}%, ahora ${pct(last.value.p)}%.`
})
</script>

<style scoped>
.wp-pulse { animation: wp-pulse 1.6s ease-out infinite; transform-box: fill-box; transform-origin: center; }
@keyframes wp-pulse { 0% { transform: scale(0.7); opacity: 0.9; } 100% { transform: scale(1.7); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .wp-pulse { animation: none; } }
</style>
