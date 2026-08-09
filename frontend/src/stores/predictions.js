import { defineStore } from 'pinia'
import api from './api.js'

export const usePredictionsStore = defineStore('predictions', {
  state: () => ({
    latest: null,
    history: [],
    detail: null,
    progress: null,
    surfaceStats: null,
    tournamentLoad: null,
    surfaceLoad: null,
    serveStats: null,
    loading: false,
    error: null
  }),
  actions: {
    async fetchLatest() {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get('/predictions/latest')
        this.latest = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchHistory(sport = null, dateFrom = null, dateTo = null, status = null, page = 1, limit = 20, matchId = null, nameQuery = null) {
      this.loading = true
      this.error = null
      try {
        const params = { skip: (page - 1) * limit, limit }
        if (sport && sport !== 'all') params.sport = sport
        if (dateFrom) params.from = dateFrom
        if (dateTo) params.to = dateTo
        if (status && status !== 'all') params.status = status
        if (matchId) params.matchId = matchId
        if (nameQuery && nameQuery.trim()) params.q = nameQuery.trim()
        const { data } = await api.get('/predictions/history', { params })
        this.history = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchDetail(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get(`/predictions/${id}/result`)
        this.detail = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchProgress(id) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.get(`/predictions/${id}/progress`)
        this.progress = data
      } catch (err) {
        this.progress = null
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    async fetchSurfaceStats(matchId) {
      try {
        const { data } = await api.get(`/matches/${matchId}/surface-stats`)
        this.surfaceStats = data
      } catch (err) {
        this.surfaceStats = null
      }
    },
    async fetchTournamentLoad(matchId) {
      try {
        const { data } = await api.get(`/matches/${matchId}/tournament-load`)
        this.tournamentLoad = data
      } catch (err) {
        this.tournamentLoad = null
      }
    },
    async fetchSurfaceLoad(matchId) {
      try {
        const { data } = await api.get(`/matches/${matchId}/surface-load`)
        this.surfaceLoad = data
      } catch (err) {
        this.surfaceLoad = null
      }
    },
    async fetchServeStats(matchId) {
      try {
        const { data } = await api.get(`/matches/${matchId}/serve-stats`)
        this.serveStats = data
      } catch (err) {
        this.serveStats = null
      }
    }
  }
})
