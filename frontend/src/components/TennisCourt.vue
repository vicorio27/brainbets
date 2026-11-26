<template>
  <div class="overflow-hidden rounded-xl bg-slate-900 ring-1 ring-slate-700">
    <svg viewBox="0 0 800 420" class="block h-auto w-full" role="img" :aria-label="`Cancha: ${names[0]} a la izquierda, ${names[1]} a la derecha`">
      <defs>
        <linearGradient id="tc-floor" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b7fb3" /><stop offset="1" stop-color="#1c6393" /></linearGradient>
        <radialGradient id="tc-ball" cx="0.35" cy="0.35" r="0.8"><stop offset="0" stop-color="#f7ff9a" /><stop offset="1" stop-color="#c8e22a" /></radialGradient>
        <filter id="tc-glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4" /></filter>
      </defs>
      <rect width="800" height="420" fill="#16402f" />
      <rect x="30" y="40" width="740" height="340" rx="8" fill="#245c46" />
      <rect x="50" y="60" width="700" height="300" fill="url(#tc-floor)" />
      <!-- the half of the player who dominates the recent points warms up with his colour -->
      <rect x="50" y="60" width="350" height="300" :fill="C1" :opacity="0.05 + 0.4 * lean0" />
      <rect x="400" y="60" width="350" height="300" :fill="C2" :opacity="0.05 + 0.4 * lean1" />
      <g stroke="#f4f8fb" stroke-width="2.2" fill="none" opacity="0.95">
        <rect x="50" y="60" width="700" height="300" />
        <line x1="50" y1="97" x2="750" y2="97" /><line x1="50" y1="323" x2="750" y2="323" />
        <line x1="212" y1="97" x2="212" y2="323" /><line x1="588" y1="97" x2="588" y2="323" />
        <line x1="212" y1="210" x2="588" y2="210" />
      </g>
      <line x1="400" y1="50" x2="400" y2="370" stroke="#0b1620" stroke-width="7" opacity="0.35" />
      <line x1="400" y1="52" x2="400" y2="368" stroke="#e8eef2" stroke-width="3" stroke-dasharray="3 3" />
      <circle cx="400" cy="50" r="4" fill="#e8eef2" /><circle cx="400" cy="370" r="4" fill="#e8eef2" />

      <circle v-if="mark" :key="mark.k" :cx="mark.x" :cy="mark.y" r="9" fill="none" :stroke="mark.out ? '#f87171' : '#ffffff'" stroke-width="2" class="tc-mark" />

      <g>
        <circle v-for="(t, i) in trail" :key="i" :cx="t.x" :cy="t.y - t.h" :r="2 + i * 0.35" fill="#e6f26b" :opacity="(i + 1) / (trail.length * 2.2)" />
      </g>

      <g v-for="k in [0, 1]" :key="k">
        <ellipse :cx="pl[k].x" :cy="pl[k].y + 15" rx="15" ry="5" fill="#000" opacity="0.3" />
        <circle v-if="swing[k]" :cx="pl[k].x" :cy="pl[k].y" r="24" :fill="k ? C2 : C1" opacity="0.3" filter="url(#tc-glow)" />
        <line :x1="pl[k].x" :y1="pl[k].y" :x2="pl[k].x + (k ? -1 : 1) * (swing[k] ? 26 : 16)" :y2="pl[k].y + (swing[k] ? -10 : 6)" stroke="#e5e7eb" stroke-width="3" stroke-linecap="round" />
        <circle :cx="pl[k].x + (k ? -1 : 1) * (swing[k] ? 28 : 18)" :cy="pl[k].y + (swing[k] ? -12 : 7)" r="8" fill="none" stroke="#e5e7eb" stroke-width="2" />
        <circle :cx="pl[k].x" :cy="pl[k].y" r="13" :fill="k ? C2 : C1" stroke="#0f172a" stroke-width="2" />
        <text :x="pl[k].x" :y="pl[k].y + 4.5" text-anchor="middle" font-size="13" font-weight="700" fill="#0f172a">{{ ini(k) }}</text>
      </g>

      <g v-if="ball.on">
        <ellipse :cx="ball.x" :cy="ball.y + 3" :rx="6" ry="2.6" fill="#000" :opacity="Math.max(0.12, 0.4 - ball.h * 0.006)" />
        <circle :cx="ball.x" :cy="ball.y - ball.h" r="9" fill="#e6f26b" opacity="0.35" filter="url(#tc-glow)" />
        <circle :cx="ball.x" :cy="ball.y - ball.h" r="6.5" fill="url(#tc-ball)" stroke="#a3bd12" stroke-width="0.8" />
      </g>

      <text x="40" y="30" font-size="15" font-weight="700" :fill="C1">{{ names[0] }}</text>
      <text x="760" y="30" font-size="15" font-weight="700" text-anchor="end" :fill="C2">{{ names[1] }}</text>

      <g v-if="banner.text" :key="banner.k" class="tc-banner">
        <text x="400" y="222" text-anchor="middle" font-size="46" font-weight="900" fill="#0b1620" opacity="0.55" stroke="#0b1620" stroke-width="8" stroke-linejoin="round">{{ banner.text }}</text>
        <text x="400" y="222" text-anchor="middle" font-size="46" font-weight="900" :fill="banner.color">{{ banner.text }}</text>
      </g>
    </svg>

    <div class="px-3 pb-2 pt-1 text-xs text-slate-200">
      <div class="mb-1 flex flex-wrap justify-between gap-x-2">
        <span :style="{ color: C1 }">{{ names[0] }} {{ Math.round(share * 100) }}%</span>
        <span class="text-slate-400">quién manda en los últimos {{ windowSize }} puntos</span>
        <span :style="{ color: C2 }">{{ Math.round((1 - share) * 100) }}% {{ names[1] }}</span>
      </div>
      <div class="flex h-3 overflow-hidden rounded-full bg-slate-700">
        <div class="transition-all duration-500" :style="{ width: share * 100 + '%', background: C1 }"></div>
        <div class="transition-all duration-500" :style="{ width: (1 - share) * 100 + '%', background: C2 }"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { COURT, KIND_TEXT } from '../utils/rally.js'

const props = defineProps({
  names: { type: Array, required: true },
  share: { type: Number, default: 0.5 }, // share of the last points won by player 1
  windowSize: { type: Number, default: 10 },
  speed: { type: Number, default: 1 }
})
const C1 = '#fbbf24'
const C2 = '#f472b6'
const ini = (k) => (props.names[k] || '?').replace(/^[^A-Za-zÀ-ÿ]*/, '').charAt(0).toUpperCase()
const lean0 = computed(() => Math.max(0, props.share - 0.5) * 2)
const lean1 = computed(() => Math.max(0, 0.5 - props.share) * 2)
// the player who is winning the recent points stands closer to the baseline, the other one is pushed back
const baseX = (k) => (k === 0 ? 24 + 46 * props.share : 776 - 46 * (1 - props.share))

const pl = reactive([{ x: 40, y: 210 }, { x: 760, y: 210 }])
const tgt = reactive({ y: [210, 210], x: [40, 760] })
const swing = reactive([false, false])
const ball = reactive({ on: false, x: 0, y: 0, h: 0 })
const trail = ref([])
const mark = ref(null)
const banner = reactive({ text: '', color: '#fff', k: 0 })
let token = 0
let markK = 0

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const frame = () => new Promise((res) => requestAnimationFrame((t) => res(t)))
const clampY = (y) => Math.max(COURT.top + 12, Math.min(COURT.bottom - 12, y))
function say(text, color) {
  banner.text = text
  banner.color = color
  banner.k += 1
}

async function segment(from, to, dur, arc, my) {
  const t0 = performance.now()
  let last = t0
  for (;;) {
    const now = await frame()
    if (my !== token) return false
    const t = Math.min(1, (now - t0) / dur)
    const dt = Math.max(0, (now - last) / 1000)
    last = now
    ball.x = from.x + (to.x - from.x) * t
    ball.y = from.y + (to.y - from.y) * t
    ball.h = arc * 4 * t * (1 - t)
    trail.value = [...trail.value.slice(-11), { x: ball.x, y: ball.y, h: ball.h }]
    for (const k of [0, 1]) {
      pl[k].y += (tgt.y[k] - pl[k].y) * Math.min(1, dt * 7)
      pl[k].x += (tgt.x[k] - pl[k].x) * Math.min(1, dt * 5)
    }
    if (t >= 1) return true
  }
}

async function play(rally) {
  const my = ++token
  const d = 520 / props.speed
  trail.value = []
  mark.value = null
  banner.text = ''
  tgt.x = [baseX(0), baseX(1)]
  let at = null
  const lastIdx = rally.shots.length - 1
  for (let i = 0; i <= lastIdx; i++) {
    const s = rally.shots[i]
    const h = s.hitter
    const o = 1 - h
    const dir = h === 0 ? 1 : -1
    let start
    if (s.serve) {
      const y = s.fromBottom ? COURT.midY + 28 : COURT.midY - 28
      tgt.y[h] = y
      tgt.y[o] = s.fromBottom ? COURT.midY - 28 : COURT.midY + 28
      ball.on = true
      const p0 = { x: baseX(h) + dir * 22, y }
      if (!(await segment(p0, p0, 280 / props.speed, 34, my))) return // ball toss
      start = p0
    } else {
      const hx = baseX(h) + dir * 22
      const hy = clampY(at.y)
      tgt.y[h] = hy
      if (!(await segment(at, { x: hx, y: hy }, d * 0.4, 20, my))) return // bounce, then to the racket
      start = { x: hx, y: hy }
    }
    swing[h] = true
    setTimeout(() => { swing[h] = false }, 170)
    const to = s.to
    const dur = s.serve ? d * 0.95 : d * (0.75 + Math.abs(to.x - start.x) / 1400)
    const unreachable = i === lastIdx && (rally.kind === 'winner' || rally.kind === 'ace')
    tgt.y[o] = clampY(pl[o].y + (to.y - pl[o].y) * (unreachable ? 0.35 : 1))
    if (s.type === 'net') {
      const stop = { x: COURT.net - dir * 4, y: to.y }
      if (!(await segment(start, stop, dur * 0.55, 26, my))) return
      mark.value = { x: stop.x, y: stop.y, out: true, k: ++markK }
      say(rally.kind === 'doublefault' ? 'DOBLE FALTA' : 'RED', '#f87171')
    } else {
      if (!(await segment(start, to, dur, s.serve ? 38 : 44, my))) return
      const out = s.type === 'long' || s.type === 'wide'
      mark.value = { x: to.x, y: to.y, out, k: ++markK }
      if (out) say(s.type === 'long' ? 'LARGA' : 'AFUERA', '#f87171')
      else if (i === lastIdx) say(KIND_TEXT[rally.kind], rally.kind === 'ace' ? '#fde047' : '#86efac')
    }
    at = { x: to.x, y: to.y }
  }
  await sleep(400 / props.speed)
  if (my !== token) return
  ball.on = false
  trail.value = []
}

function flash(text, color = '#fde047') {
  say(text, color)
}

function reset() {
  token += 1
  ball.on = false
  trail.value = []
  mark.value = null
  banner.text = ''
  tgt.y = [210, 210]
  tgt.x = [baseX(0), baseX(1)]
  pl[0].x = baseX(0)
  pl[0].y = 210
  pl[1].x = baseX(1)
  pl[1].y = 210
}
reset()

onBeforeUnmount(() => { token += 1 })
defineExpose({ play, reset, flash })
</script>

<style scoped>
.tc-banner { animation: tc-pop 1.1s ease-out forwards; transform-origin: 400px 210px; }
@keyframes tc-pop { 0% { opacity: 0; transform: scale(0.6); } 15% { opacity: 1; transform: scale(1.12); } 30% { transform: scale(1); } 80% { opacity: 1; } 100% { opacity: 0; } }
.tc-mark { animation: tc-ring 0.9s ease-out forwards; transform-box: fill-box; transform-origin: center; }
@keyframes tc-ring { 0% { opacity: 1; transform: scale(0.4); } 100% { opacity: 0; transform: scale(2.4); } }
@media (prefers-reduced-motion: reduce) { .tc-banner, .tc-mark { animation-duration: 0.01s; } }
</style>
