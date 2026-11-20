<template>
  <!-- Finished: one slim line of result, nothing to decide any more -->
  <router-link
    v-if="finished"
    :to="{ path: '/predictions', query: { matchId: match.matchId, date: match.eventDate } }"
    class="block bg-slate-50 rounded-lg border border-slate-200 px-4 py-2.5 hover:border-blue-400 transition-colors"
  >
    <div class="flex items-center justify-between gap-3 text-xs text-slate-500">
      <span class="truncate">{{ match.tournament || match.league }}</span>
      <span class="whitespace-nowrap">{{ match.status === 'CANCELLED' ? 'Anulado' : 'Final' }} · {{ formatDateTime(match.eventDate, match.eventTime) }}</span>
    </div>
    <div class="mt-0.5 flex flex-wrap items-baseline gap-x-3 text-sm text-slate-800">
      <span class="font-medium">{{ sport === 'tennis' ? match.player1 : match.homeTeam }} <span class="text-slate-400">vs</span> {{ sport === 'tennis' ? match.player2 : match.awayTeam }}</span>
      <span v-if="scoreLine" class="font-bold text-slate-900">{{ scoreLine }}</span>
      <span v-if="setScoresStr" class="text-xs text-slate-500">{{ setScoresStr }}</span>
    </div>
  </router-link>

  <router-link
    v-else
    :to="{ path: '/predictions', query: { matchId: match.matchId, date: match.eventDate } }"
    class="block bg-white rounded-lg shadow-sm border border-slate-200 p-4 hover:border-blue-400 hover:shadow-md transition-all cursor-pointer"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="flex-1 min-w-0">
        <!-- Layer 1: what and when -->
        <div class="flex items-center justify-between gap-2 mb-2 text-xs sm:text-sm">
          <span class="font-medium text-slate-500 truncate">{{ match.tournament || match.league }}</span>
          <span class="flex items-center gap-2 flex-shrink-0">
            <span
              v-if="bestConfidence != null"
              :class="isTop ? 'bg-orange-100 text-orange-800' : 'bg-slate-100 text-slate-700'"
              class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap"
              :title="isTop ? 'Top 3: mayor confianza del día' : 'Confianza de la mejor predicción'"
            >{{ bestConfidence }}%</span>
            <span v-if="match.eventDate" class="text-slate-600 whitespace-nowrap">{{ formatDateTime(match.eventDate, match.eventTime) }}</span>
            <span v-else-if="match.eventTime && match.eventTime !== '00:00'" class="text-slate-600">{{ formatTime(match.eventTime) }}</span>
          </span>
        </div>
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-3">
          <div class="text-base sm:text-lg font-semibold text-slate-900 truncate">
            {{ sport === 'tennis' ? match.player1 : match.homeTeam }}
            <span v-if="favInfo" :class="favInfo.p1.cls" :title="favInfo.title" class="ml-1 align-middle inline-flex px-2 py-0.5 rounded-full text-xs font-semibold">{{ favInfo.p1.text }}</span>
          </div>
          <div class="text-sm text-slate-500 px-0 sm:px-3 flex-shrink-0">vs</div>
          <div class="text-base sm:text-lg font-semibold text-slate-900 truncate">
            {{ sport === 'tennis' ? match.player2 : match.awayTeam }}
            <span v-if="favInfo" :class="favInfo.p2.cls" :title="favInfo.title" class="ml-1 align-middle inline-flex px-2 py-0.5 rounded-full text-xs font-semibold">{{ favInfo.p2.text }}</span>
          </div>
        </div>
        <div class="mt-1 text-xs text-slate-500">
          <span v-if="sport === 'tennis' && match.surface">{{ match.surface }}</span>
          <span v-if="sport === 'tennis' && match.rankingPlayer1"><template v-if="match.surface"> · </template>Ranking #{{ match.rankingPlayer1 }} vs #{{ match.rankingPlayer2 }}</span>
          <span v-if="sport === 'football' && match.homePosition">Posición {{ match.homePosition }} vs {{ match.awayPosition }}</span>
          <span v-if="!(match.eventTime && match.eventTime !== '00:00') && match.eventDate"> · Hora por confirmar</span>
        </div>
        <div v-if="favInfo && favInfo.note" class="mt-1 text-xs text-amber-800">{{ favInfo.note }}</div>
        <div v-for="s in newsStakes" :key="s.headline" class="mt-1 text-xs text-amber-900" :title="`${s.headline} (${s.source}, ${s.date})`">
          🏆 <span class="font-medium">En juego:</span> {{ s.note || s.headline }}
        </div>
        <router-link v-if="inPlayWindow" to="/en-vivo" class="mt-1 inline-block text-xs font-medium text-red-700 underline">🔴 Ver en vivo</router-link>
        <!-- Live / result score -->
        <div v-if="scoreLine" class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
          <span
            v-if="match.status === 'LIVE'"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse"></span> EN VIVO
          </span>
          <span
            v-else
            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-200 text-slate-700"
          >Final</span>
          <span class="text-sm font-bold text-slate-900">{{ scoreLine }}</span>
          <span v-if="setScoresStr" class="text-xs text-slate-500">{{ setScoresStr }}</span>
        </div>

        <!-- Layer 2: the bets, which is what gets decided -->
        <!-- Most likely bets, however little they pay (likely_picks_service) -->
        <div v-if="likelyPicks.length" class="mt-2 rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-xs text-slate-700">
          <div class="font-medium text-emerald-800">✅ Lo más probable</div>
          <template v-for="(p, i) in likelyPicks" :key="p.label">
          <div v-if="p.group === 'games' && (i === 0 || likelyPicks[i - 1].group !== 'games')" class="mt-1.5 border-t border-emerald-200 pt-1 font-medium text-emerald-800">🎾 Games y tiebreaks</div>
          <div class="mt-1 flex items-baseline gap-1.5" :title="pickTitle(p)">
            <span class="w-9 shrink-0 font-semibold text-slate-900">{{ Math.round(p.probability * 100) }}%</span>
            <span class="min-w-0 flex-1">
              {{ p.label }}
              <span class="block text-slate-600"><template v-if="p.source === 'modelo'"><span class="font-medium text-amber-800">modelo, sin cuota de la casa</span> · </template>{{ p.oddsKind === 'aprox' ? 'cuota ≈' : 'cuota ' }}{{ p.odds.toFixed(2) }} · +${{ p.payPer100 }} por $100<template v-if="p.history"> · antes salió {{ Math.round(p.history.winRate * 100) }}% de {{ p.history.n }}</template></span>
            </span>
            <button
              class="shrink-0 self-center rounded border px-1.5 text-sm font-semibold leading-5"
              :class="combo.has(pickKey(p)) ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-emerald-300 bg-white text-emerald-800 hover:bg-emerald-100'"
              :aria-label="combo.has(pickKey(p)) ? `Quitar de mi combinada: ${p.label}` : `Agregar a mi combinada: ${p.label}`"
              :title="combo.has(pickKey(p)) ? 'Está en tu combinada (toca para quitarla)' : 'Agregar a mi combinada'"
              @click.stop.prevent="togglePick(p)"
            >{{ combo.has(pickKey(p)) ? '✓' : '+' }}</button>
          </div>
          </template>
          <div v-if="clash" class="mt-1.5 rounded bg-amber-50 px-2 py-1 text-amber-800">
            Ya tienes «{{ clash.current.label }}» de este partido. Dos apuestas del mismo partido dependen una de la otra.
            <button class="ml-1 font-semibold underline" @click.stop.prevent="replaceClash">cambiarla por esta</button>
            <button class="ml-1 underline" @click.stop.prevent="clash = null">dejarla</button>
          </div>
        </div>


        <!-- Layer 3: everything else, folded -->
        <details v-if="hasMore" class="mt-2 text-xs text-slate-700" @click.stop>
          <summary class="cursor-pointer text-slate-600">Más datos<span v-if="moreHint" class="text-slate-500"> · {{ moreHint }}</span></summary>
        <!-- Head-to-head from our DB (every stored meeting between these two players) -->
        <div v-if="sport === 'tennis'" class="mt-2 text-xs text-slate-600" :title="h2hTitle">
          <template v-if="h2hInfo">
            <span class="font-medium">H2H:</span>
            {{ match.player1 }} <span class="font-semibold text-slate-900">{{ h2hInfo.p1Wins }}-{{ h2hInfo.p2Wins }}</span> {{ match.player2 }}
            <span class="text-slate-500"> · último: {{ h2hInfo.last.tournament }} {{ h2hInfo.last.date.slice(0, 4) }},
              ganó {{ h2hInfo.last.winner === 'p1' ? match.player1 : match.player2 }}<template v-if="h2hInfo.last.sets">&nbsp;({{ h2hInfo.last.sets }})</template></span>
          </template>
          <span v-else class="text-slate-500">H2H: nunca se han enfrentado (en los partidos guardados desde 2010)</span>
        </div>
        <!-- Tournament streaks (information, already in the price) -->
        <div v-if="streakRows.length" class="mt-2 space-y-1">
          <div v-for="row in streakRows" :key="row.name" class="flex flex-wrap items-center gap-1 text-xs">
            <span class="font-medium text-slate-600">{{ row.name }}</span>
            <span
              v-for="t in row.tags"
              :key="t.key"
              class="inline-flex items-center px-2 py-0.5 rounded-full font-medium"
              :class="t.cls"
              :title="t.title"
            >{{ t.text }}</span>
          </div>
        </div>

        <div v-if="newsCount" class="mt-1 text-xs text-slate-700" title="Noticias fuera de la cancha de esta semana: ábrelo para leerlas">
          📰 {{ newsCount }} {{ newsCount === 1 ? 'noticia' : 'noticias' }} a tener en cuenta<template v-if="newsNegative">&nbsp;· <span class="text-red-700 font-medium">{{ newsNegative }} {{ newsNegative === 1 ? 'negativa' : 'negativas' }} para un jugador</span></template>
        </div>

        <div v-for="lv in levelLines" :key="lv.player" class="mt-1 text-xs" :class="LEVEL_CLASS[lv.r.level]" :title="lv.tip">
          📊 <span class="font-medium">{{ lv.player }}:</span> {{ lv.r.headline }}
        </div>
        <details v-if="latestNews" class="mt-1 text-xs text-slate-700" @click.stop>
          <summary class="cursor-pointer">📰 Últimas noticias de cada jugador ({{ latestNews.total }})</summary>
          <div v-for="side in latestNews.sides" :key="side.key" class="mt-1">
            <div class="font-medium text-slate-800">{{ side.name }}</div>
            <p v-if="!side.items.length" class="text-slate-500">Sin noticias en los últimos 5 días.</p>
            <ul v-else class="space-y-0.5">
              <li v-for="it in side.items" :key="it.link">
                <a :href="it.link" target="_blank" rel="noopener noreferrer" class="text-blue-700 hover:underline break-words">{{ it.headline }}</a>
                <span class="text-slate-500"> · {{ it.source }} · {{ newsAgo(it.published) }}</span>
              </li>
            </ul>
          </div>
        </details>

        <div v-if="dogCase" class="mt-1 text-xs text-slate-700" :title="dogTitle">
          🎯 <template v-if="dogCase.headline">{{ dogCase.headline.replace(/, ya que:$/, '') }} ({{ dogCase.reasons.length }} {{ dogCase.reasons.length === 1 ? 'argumento' : 'argumentos' }})</template><span v-else class="text-slate-500">No favorito: {{ dogCase.underdog }}<template v-if="dogCase.odds">&nbsp;a {{ dogCase.odds }}</template> · sin argumentos con datos a su favor</span>
        </div>

        <!-- Frozen games model (information; its lab is still collecting sample) -->
        <div
          v-if="gamesInfo"
          class="mt-2 rounded border px-2 py-1.5 text-xs"
          :class="gamesInfo.close ? 'border-sky-200 bg-sky-50 text-slate-700' : 'border-slate-200 bg-slate-50 text-slate-600'"
          title="Modelo de games (saque y resto, juego a juego), congelado el 16-oct-2026. No ha demostrado ganarle a la casa: se está midiendo en Caja → Laboratorio."
        >
          <span v-if="gamesInfo.close" class="font-semibold text-sky-800">⚖ Partido reñido · </span>
          <span class="font-medium">Modelo de games:</span>
          ~{{ gamesInfo.g.expectedGames }} games · tiebreak {{ gamesInfo.tiebreak }}% · {{ gamesInfo.deciderLabel }} {{ gamesInfo.decider }}%
          <template v-if="gamesInfo.g.line">
            <span class="block">
              Línea {{ gamesInfo.g.line.line }}: Más según el modelo {{ gamesInfo.modelOver }}% · según la casa {{ gamesInfo.marketOver }}%
              (Más {{ gamesInfo.g.line.over.toFixed(2) }} / Menos {{ gamesInfo.g.line.under.toFixed(2) }})
            </span>
          </template>
          <span v-if="gamesInfo.g.trust < 0.5" class="block text-slate-500">Poca historia de saque y resto de alguno de los dos.</span>
        </div>

        <!-- Prediction reliability by player on this surface -->
        <div v-if="reliabilityRows.length" class="mt-2 space-y-0.5 text-xs">
          <div v-for="row in reliabilityRows" :key="row.name" class="text-slate-500">
            <span class="font-medium text-slate-600">{{ row.name }}</span>
            <span v-if="row.best" class="text-green-700"> · ✓ {{ row.best.label }} {{ row.best.hitRate }}%</span>
            <span v-if="row.worst" class="text-red-700"> · ✗ {{ row.worst.label }} {{ row.worst.hitRate }}%</span>
            <span class="text-slate-500"> ({{ row.sampleTotal }} preds en {{ match.surface }})</span>
          </div>
        </div>
        </details>
      </div>
    </div>
  </router-link>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useComboStore, legKey } from '../stores/combo.js'
import { formatDateTime, formatDate, formatTime } from '../utils/format.js'
import { streakTags } from '../utils/streak.js'

const props = defineProps({
  match: {
    type: Object,
    required: true
  },
  sport: {
    type: String,
    required: true
  },
  bestConfidence: {
    type: Number,
    default: null
  },
  isTop: {
    type: Boolean,
    default: false
  },
  // { player1: { best, worst, markets, sampleTotal } | null, player2: {...} | null }
  reliability: {
    type: Object,
    default: null
  }
})

const newsItems = computed(() => {
  const n = props.match.playerNews
  if (props.sport !== 'tennis' || !n || props.match.status === 'FINISHED') return []
  return [...(n.player1 || []), ...(n.player2 || [])]
})
const newsCount = computed(() => newsItems.value.length)
// Finished or cancelled matches render as one slim line
const finished = computed(() => ['FINISHED', 'CANCELLED'].includes(props.match.status))
// From 10 min before its time to 6 h after (same window as routers/live.py), link to En vivo
const inPlayWindow = computed(() => {
  if (props.sport !== 'tennis' || ['FINISHED', 'CANCELLED'].includes(props.match.status)) return false
  if (!props.match.eventDate || !props.match.eventTime) return false
  const start = new Date(`${props.match.eventDate}T${props.match.eventTime}:00-05:00`).getTime()
  const now = Date.now()
  return now >= start - 10 * 60000 && now <= start + 6 * 3600000
})
// How each player is playing lately against his own usual level (form_service); "normal" is not shown
const LEVEL_CLASS = { bien: 'text-emerald-800', mal: 'text-red-700', mixto: 'text-slate-700', leve: 'text-slate-600' }
const levelLines = computed(() => {
  if (props.sport !== 'tennis' || props.match.status === 'FINISHED') return []
  return [[props.match.player1, props.match.levelPlayer1], [props.match.player2, props.match.levelPlayer2]]
    .filter(([, r]) => r && r.level !== 'normal')
    .map(([player, r]) => ({
      player, r,
      tip: r.metrics.map((m) => (m.trend === 'mejor' ? '▲ ' : m.trend === 'peor' ? '▼ ' : '= ') + m.text).join('\n') + '\n\n' + r.note
    }))
})
// The newest headlines of each player as they are (no AI filter), refreshed hourly before the match
const latestNews = computed(() => {
  const l = props.match.playerNews?.latest
  if (props.sport !== 'tennis' || !l) return null
  const sides = [
    { key: 'p1', name: props.match.player1, items: l.player1 || [] },
    { key: 'p2', name: props.match.player2, items: l.player2 || [] }
  ]
  const total = sides[0].items.length + sides[1].items.length
  return total ? { sides, total } : null
})
function newsAgo(iso) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 60) return `hace ${mins} min`
  if (mins < 48 * 60) return `hace ${Math.round(mins / 60)} h`
  return `hace ${Math.round(mins / 1440)} días`
}
const newsStakes = computed(() => newsItems.value.filter(i => i.factor === 'en_juego').slice(0, 2))
const newsNegative = computed(() => newsItems.value.filter(i => i.impact === 'negativo').length)
const likelyPicks = computed(() => (props.sport === 'tennis' ? props.match.likelyPicks || [] : []))
const combo = useComboStore()
const clash = ref(null)
const pickKey = (p) => legKey(props.match.matchId, p.label)
function pickLeg(p) {
  return {
    key: pickKey(p), matchId: props.match.matchId, match: `${props.match.player1} vs ${props.match.player2}`,
    eventDate: props.match.eventDate, eventTime: props.match.eventTime,
    label: p.label, kind: p.kind, selector: p.selector, probability: p.probability, odds: p.odds, oddsKind: p.oddsKind,
    bestOdds: p.bestOdds || p.odds, bestBook: p.bestBook || null, bestNeedsCheck: !!p.bestNeedsCheck
  }
}
function togglePick(p) {
  clash.value = null
  if (combo.has(pickKey(p))) { combo.remove(pickKey(p)); return }
  const current = combo.add(pickLeg(p))
  if (current) clash.value = { current, leg: pickLeg(p) }
}
function replaceClash() {
  combo.replace(clash.value.leg)
  clash.value = null
}
const pickTitle = (p) => {
  const who = p.source === 'modelo' ? 'el modelo de saque y resto le da' : 'la casa le da'
  const lines = [`${p.label}: ${who} ${Math.round(p.probability * 100)}%${p.source === 'modelo' ? '' : ' (sin su margen)'}; pierdes ${Math.round(p.lossProbability * 100)} de cada 100 veces.`]
  lines.push(p.oddsKind === 'aprox' ? `Cuota estimada ≈${p.odds.toFixed(2)}: confírmala en la casa.` : `Cuota de la casa: ${p.odds.toFixed(2)}.`)
  if (p.note) lines.push(p.note)
  const h = p.history
  if (h) {
    let s = `Apuestas como esta (tramo ${p.band}%): salieron ${Math.round(h.winRate * 100)}% de ${h.n}, se esperaba ${Math.round(h.expected * 100)}%.`
    if (h.yield != null) s += ` A la cuota de la casa rindieron ${(h.yield * 100).toFixed(1)}% por apuesta (rango probable ${(h.yieldLow * 100).toFixed(1)}% a ${(h.yieldHigh * 100).toFixed(1)}%).`
    lines.push(s)
  }
  lines.push('Lo más probable no es lo más rentable: la casa cobra su margen también aquí.')
  return lines.join('\n')
}
const dogCase = computed(() => (props.sport === 'tennis' ? props.match.underdogCase : null))
const dogTitle = computed(() => {
  const c = dogCase.value
  if (!c) return ''
  if (!c.reasons.length) return `La casa le da ${Math.round(c.marketProb * 100)}% a ${c.underdog} y no hay ningún dato que diga que es más.`
  return c.headline + '\n' + c.reasons.map(r => '• ' + r.text).join('\n') + '\n\n' + c.note
})
const h2hInfo = computed(() => {
  const h = props.match.h2hDetail
  if (!h || !h.meetings?.length) return null
  return { ...h, last: h.meetings[0] }
})
const h2hTitle = computed(() => {
  const h = h2hInfo.value
  if (!h) return 'Sin partidos entre ellos en nuestra base (ATP desde 2010).'
  const surf = { hard: 'cemento', clay: 'arcilla', grass: 'césped' }
  return h.meetings
    .map(m => `${m.date} · ${m.tournament || '?'}${m.surface ? ' (' + (surf[m.surface] || m.surface) + ')' : ''} · ganó ${m.winner === 'p1' ? props.match.player1 : props.match.player2}${m.sets ? ' ' + m.sets : ''}${m.games ? ' · ' + m.games.join(' ') : ''}`)
    .join('\n') + (h.total > h.meetings.length ? `\n… y ${h.total - h.meetings.length} más` : '')
})
// Favourite = the side the bookmaker prices shorter (its fair probability),
// not the better ranking: the price already weighs surface, form and fatigue.
const favInfo = computed(() => {
  if (props.sport !== 'tennis') return null
  const m = props.match
  const mw = m.oddsMarkets?.matchWinner
  let p1 = null
  let source = 'casa'
  if (mw?.p1 > 1 && mw?.p2 > 1) p1 = (1 / mw.p1) / (1 / mw.p1 + 1 / mw.p2)
  else if (m.gamesModel?.markets?.matchP1 != null && (m.gamesModel.trust ?? 0) >= 0.2) {
    p1 = m.gamesModel.markets.matchP1
    source = 'modelo'
  }
  if (p1 == null) return null
  const pct = (x) => Math.round(x * 100)
  const even = Math.abs(p1 - 0.5) < 0.05
  const tag = (prob) => even
    ? { text: `Parejo ${pct(prob)}%`, cls: 'bg-slate-100 text-slate-700' }
    : prob > 0.5
      ? { text: `Favorito ${pct(prob)}%`, cls: 'bg-emerald-100 text-emerald-800' }
      : { text: `No favorito ${pct(prob)}%`, cls: 'bg-amber-100 text-amber-800' }
  const favP1 = p1 > 0.5
  const r1 = m.rankingPlayer1
  const r2 = m.rankingPlayer2
  let note = null
  if (!even && r1 && r2 && r1 !== r2 && (favP1 ? r1 > r2 : r2 > r1)) {
    const [fav, rf, ro] = favP1 ? [m.player1, r1, r2] : [m.player2, r2, r1]
    const surf = { hard: 'cemento', clay: 'arcilla', grass: 'césped' }[m.surface] || m.surface
    note = `${fav} es favorito pese al ranking (#${rf} vs #${ro})${surf ? ': la cuota pesa también la superficie (' + surf + '), la forma y el cansancio' : ''}.`
  }
  const title = source === 'casa'
    ? 'Probabilidad de ganar el partido según la cuota de la casa, sin su margen. Ya incluye superficie, forma, cansancio y cara a cara; por eso puede no coincidir con el ranking.'
    : 'La casa no publicó cuota: probabilidad del modelo de saque y resto (no le ha ganado a la cuota).'
  return { p1: tag(p1), p2: tag(1 - p1), note, title }
})
const gamesInfo = computed(() => {
  const g = props.match.gamesModel
  if (props.sport !== 'tennis' || !g || props.match.status === 'FINISHED') return null
  const mw = props.match.oddsMarkets?.matchWinner
  let close = false
  if (mw?.p1 > 1 && mw?.p2 > 1) {
    const fair = (1 / mw.p1) / (1 / mw.p1 + 1 / mw.p2)
    close = fair >= 0.4 && fair <= 0.6
  }
  const pct = (x) => Math.round(x * 100)
  return {
    g,
    close,
    tiebreak: pct(g.tiebreak),
    decider: pct(g.decider),
    deciderLabel: g.bestOf === 5 ? '4 o 5 sets' : '3er set',
    modelOver: g.line ? pct(g.line.modelOver) : null,
    marketOver: g.line ? pct(g.line.marketOver) : null
  }
})
const streakRows = computed(() => {
  if (props.sport !== 'tennis' || props.match.status === 'FINISHED') return []
  return [[props.match.player1, props.match.streakPlayer1], [props.match.player2, props.match.streakPlayer2]]
    .map(([name, s]) => ({ name, tags: streakTags(s) }))
    .filter(r => r.tags.length)
})

// Live / final score line, from our DB (no api-tennis call).
const scoreLine = computed(() => {
  const m = props.match
  if (props.sport === 'tennis') {
    if (m.status === 'FINISHED' && m.finalSets) {
      return m.winner ? `${m.finalSets} · ${m.winner}` : m.finalSets
    }
    if (m.status === 'LIVE' && m.liveSets) {
      const g = m.liveGames ? ` · ${m.liveGames}` : ''
      const p = m.livePeriod ? ` (${m.livePeriod})` : ''
      return `${m.liveSets} sets${g}${p}`
    }
    return null
  }
  // football
  if (m.homeScore != null && m.awayScore != null && (m.status === 'LIVE' || m.status === 'FINISHED')) {
    return `${m.homeScore}-${m.awayScore}`
  }
  return null
})
const setScoresStr = computed(() => {
  const s = props.match.setScores
  if (!Array.isArray(s) || !s.length) return null
  return s.map((x) => `${x[0]}-${x[1]}`).join('  ')
})

// One compact line per player that has enough validated history on this surface.
const reliabilityRows = computed(() => {
  const r = props.reliability
  if (!r) return []
  const rows = []
  const add = (name, blk) => {
    if (blk && (blk.best || blk.worst)) {
      rows.push({ name, best: blk.best, worst: blk.worst, sampleTotal: blk.sampleTotal })
    }
  }
  add(props.match.player1, r.player1)
  add(props.match.player2, r.player2)
  return rows
})

// Layer 3 teaser: what is inside "Más datos"
const moreHint = computed(() => {
  const t = []
  if (h2hInfo.value) t.push(`H2H ${h2hInfo.value.p1Wins}-${h2hInfo.value.p2Wins}`)
  if (latestNews.value) t.push(`${latestNews.value.total} noticias`)
  if (levelLines.value.length) t.push('cómo vienen jugando')
  if (dogCase.value) t.push('no favorito')
  if (gamesInfo.value) t.push('modelo de games')
  return t.join(' · ')
})
const hasMore = computed(() => props.sport === 'tennis' || streakRows.value.length > 0 || reliabilityRows.value.length > 0)
</script>
