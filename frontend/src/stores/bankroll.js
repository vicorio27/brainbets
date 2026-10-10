import { defineStore } from 'pinia'
import api from './api.js'

export const useBankrollStore = defineStore('bankroll', {
  state: () => ({
    simulation: null,
    lab: null,
    loading: false,
    error: null
  }),
  actions: {
    async simulate(params) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/analytics/bankroll', { params })
        this.simulation = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
        this.simulation = null
      } finally {
        this.loading = false
      }
    },
    async fetchLab() {
      try {
        const { data } = await api.get('/analytics/lab')
        this.lab = data
      } catch (err) {
        this.lab = null
      }
    }
  }
})
