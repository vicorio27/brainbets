import { defineStore } from 'pinia'
import api from './api.js'

export const useMatchesStore = defineStore('matches', {
  state: () => ({
    latest: null,
    playerSetStats: null,
    loading: false,
    error: null
  }),
  actions: {
    async fetchLatest() {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/matches/latest')
        this.latest = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchByDate(date) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/matches/by-date', {
          params: { from: date, to: date }
        })
        this.latest = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchHistory(from, to, sport = null, page = 1, limit = 20, sort = 'desc') {
      this.loading = true
      this.error = null
      try {
        const params = { from, to, skip: (page - 1) * limit, limit, sort }
        if (sport && sport !== 'all') params.sport = sport
        const { data } = await api.get('/matches/by-date', { params })
        this.latest = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchPlayerSetStats(date = null) {
      try {
        const params = date ? { date } : {}
        const { data } = await api.get('/matches/player-set-stats', { params })
        this.playerSetStats = data
      } catch (err) {
        this.playerSetStats = null
      }
    }
  }
})
