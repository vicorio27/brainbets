<template>
  <details v-if="show" class="mt-2 rounded border border-slate-200 bg-white">
    <summary class="cursor-pointer px-2.5 py-1.5 text-xs font-medium text-slate-800">
      Noticias antes del partido
      <span class="font-normal text-slate-500">· {{ hint }}</span>
    </summary>
    <div class="space-y-2 border-t border-slate-100 px-2.5 py-2 text-xs text-slate-700">
      <template v-if="news">
        <div v-for="[team, items] in teams" :key="team">
          <div class="font-medium text-slate-800">{{ team }}</div>
          <p v-if="!items.length" class="text-slate-500">Sin titulares relevantes en los últimos 5 días.</p>
          <ul v-else class="space-y-1">
            <li v-for="n in items" :key="n.link || n.headline">
              <span v-for="t in n.tags" :key="t" class="mr-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase" :class="TAG[t].cls">{{ TAG[t].text }}</span>
              <a :href="n.link" target="_blank" rel="noopener noreferrer" class="text-blue-700 hover:underline">{{ n.headline }}</a>
              <span class="text-slate-500"> · {{ n.source }} · {{ ago(n.published) }}</span>
            </li>
          </ul>
        </div>
        <p class="text-slate-500">
          Leído {{ ago(news.fetchedAt) }}<span v-if="news.prematchAt"> y otra vez justo antes del partido</span>. Solo titulares de prensa
          (Google Noticias): no incluye lo que se diga en la última hora ni la alineación oficial. Es información, no una señal medida contra la cuota.
        </p>
      </template>
      <p v-else class="text-slate-500">
        Todavía no se han leído noticias de este partido. Se leen desde unas 30 horas antes del inicio, cada hora, y una vez más media hora antes.
      </p>
    </div>
  </details>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ news: { type: Object, default: null }, home: String, away: String, status: String })

const TAG = {
  lesion: { text: 'lesión', cls: 'bg-red-100 text-red-800' },
  sancion: { text: 'sanción', cls: 'bg-orange-100 text-orange-800' },
  entrenador: { text: 'entrenador', cls: 'bg-purple-100 text-purple-800' },
  alineacion: { text: 'alineación', cls: 'bg-sky-100 text-sky-800' },
  en_juego: { text: 'en juego', cls: 'bg-emerald-100 text-emerald-800' }
}

const show = computed(() => props.status === 'SCHEDULED' || !!props.news)
const teams = computed(() => [[props.home, props.news?.home || []], [props.away, props.news?.away || []]])
const hint = computed(() => {
  if (!props.news) return 'sin leer todavía'
  const all = [...(props.news.home || []), ...(props.news.away || [])]
  const hurt = all.filter((n) => n.tags.includes('lesion') || n.tags.includes('sancion')).length
  return `${all.length} titulares${hurt ? ` · ${hurt} de lesión o sanción` : ''}`
})

function ago(iso) {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (min < 60) return `hace ${min} min`
  if (min < 1440) return `hace ${Math.round(min / 60)} h`
  return `hace ${Math.round(min / 1440)} d`
}
</script>
