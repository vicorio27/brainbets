<template>
  <!-- One category of data: the title and its headline number are always visible; the detail opens in place -->
  <details class="rounded border border-slate-200 bg-white" @click.stop>
    <summary class="flex cursor-pointer items-center justify-between gap-3 px-2.5 py-2 text-xs">
      <span class="font-medium text-slate-800">{{ title }}</span>
      <span v-if="hint" class="min-w-0 truncate text-right text-slate-500">{{ hint }}</span>
    </summary>
    <div class="space-y-1 border-t border-slate-100 px-2.5 py-2 text-xs text-slate-700">
      <slot />
    </div>
  </details>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' }
})
</script>
