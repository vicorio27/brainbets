<template>
  <div class="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
    <div class="flex items-center justify-between mb-2">
      <div class="text-2xl">{{ icon }}</div>
      <div
        class="text-2xl font-bold"
        :class="{
          'text-green-600': color === 'green',
          'text-yellow-600': color === 'yellow',
          'text-red-600': color === 'red',
          'text-slate-900': color === 'gray' || !color
        }"
      >
        {{ value }}
      </div>
    </div>
    <div class="text-sm text-slate-600">{{ title }}</div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  value: [String, Number],
  icon: String,
  color: {
    type: String,
    default: 'gray'
  }
})
</script>
