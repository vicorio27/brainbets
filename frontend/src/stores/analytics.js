import { defineStore } from 'pinia'
import api from './api.js'

export const useAnalyticsStore = defineStore('analytics', {
  state: () => ({
    accuracy: null,
    accuracyByDay: null,
    dashboard: null,
    loading: false,
    error: null
  }),
  actions: {
    async fetchAccuracy() {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/analytics/accuracy')
        this.accuracy = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchAccuracyByDay(days = 60) {
      try {
        const { data } = await api.get('/analytics/accuracy-by-day', { params: { days } })
        this.accuracyByDay = data.days || []
      } catch (err) {
        this.accuracyByDay = []
      }
    },
    async fetchDashboard() {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/analytics/dashboard')
        this.dashboard = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    }
  }
})
