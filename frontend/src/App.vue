<template>
  <div class="min-h-screen bg-slate-50">
    <nav class="bg-white shadow-sm border-b border-slate-200">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <div class="flex items-center">
            <router-link to="/" class="flex items-center gap-2">
              <div class="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">
                B
              </div>
              <span class="text-xl font-bold text-slate-900">BrainBets</span>
            </router-link>
          </div>
          <div class="hidden sm:flex items-center gap-6">
            <router-link to="/" class="text-sm font-medium text-slate-600 hover:text-blue-600">
              Dashboard
            </router-link>
            <router-link to="/matches" class="text-sm font-medium text-slate-600 hover:text-blue-600">
              Partidos
            </router-link>
            <router-link to="/predictions" class="text-sm font-medium text-slate-600 hover:text-blue-600">
              Predicciones
            </router-link>
            <router-link to="/analytics" class="text-sm font-medium text-slate-600 hover:text-blue-600">
              Analytics
            </router-link>
          </div>
          <div class="flex items-center sm:hidden">
            <button
              @click="mobileMenuOpen = !mobileMenuOpen"
              class="inline-flex items-center justify-center p-2 rounded-md text-slate-600 hover:text-blue-600 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-500"
              aria-label="Abrir menú"
            >
              <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path v-if="!mobileMenuOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
                <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
      <div v-if="mobileMenuOpen" class="sm:hidden border-t border-slate-200">
        <div class="px-2 pt-2 pb-3 space-y-1">
          <router-link
            to="/"
            @click="mobileMenuOpen = false"
            class="block px-3 py-2 rounded-md text-base font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50"
            :class="{ 'bg-slate-50 text-blue-600': $route.path === '/' }"
          >
            Dashboard
          </router-link>
          <router-link
            to="/matches"
            @click="mobileMenuOpen = false"
            class="block px-3 py-2 rounded-md text-base font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50"
            :class="{ 'bg-slate-50 text-blue-600': $route.path === '/matches' }"
          >
            Partidos
          </router-link>
          <router-link
            to="/predictions"
            @click="mobileMenuOpen = false"
            class="block px-3 py-2 rounded-md text-base font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50"
            :class="{ 'bg-slate-50 text-blue-600': $route.path === '/predictions' }"
          >
            Predicciones
          </router-link>
          <router-link
            to="/analytics"
            @click="mobileMenuOpen = false"
            class="block px-3 py-2 rounded-md text-base font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50"
            :class="{ 'bg-slate-50 text-blue-600': $route.path === '/analytics' }"
          >
            Analytics
          </router-link>
        </div>
      </div>
    </nav>
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const mobileMenuOpen = ref(false)
</script>
