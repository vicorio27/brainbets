import { defineStore } from 'pinia'
import api from './api.js'

// The user's registered bets (singles and combos), settled by the backend on results.
export const useMyBetsStore = defineStore('mybets', {
  state: () => ({
    data: null,
    loading: false,
    error: null
  }),
  actions: {
    async fetch() {
      this.loading = true
      this.error = null
      try {
        // Never from the GET cache: a bet registered a second ago must show up.
        const { data } = await api.get('/my-bets', { noCache: true })
        this.data = data
      } catch (err) {
        this.error = err.response?.data?.detail || err.message
      } finally {
        this.loading = false
      }
    },
    // legs: the combo store's legs; uses the price the user typed (myOdds).
    async register(amount, legs) {
      const payload = {
        amount,
        legs: legs.map((l) => ({
          matchId: l.matchId,
          kind: l.kind,
          selector: l.selector,
          label: l.label,
          odds: l.myOdds || l.odds,
          probability: l.probability,
          bestOdds: l.bestOdds || null
        }))
      }
      const { data } = await api.post('/my-bets', payload)
      return data
    },
    async remove(id) {
      await api.delete(`/my-bets/${id}`)
      await this.fetch()
    }
  }
})
