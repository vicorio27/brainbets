import { defineStore } from 'pinia'

// The user's own parlay, built from the "Lo más probable" picks of each match.
// Kept in this browser only (localStorage), so it survives a reload.
const KEY = 'brainbets.combo.v1'

function load() {
  try {
    const raw = localStorage.getItem(KEY)
    const data = raw ? JSON.parse(raw) : null
    if (data && Array.isArray(data.legs)) return { legs: data.legs, amount: Number(data.amount) || 100000 }
  } catch (e) { /* private window or blocked storage: start empty */ }
  return { legs: [], amount: 100000 }
}

export function legKey(matchId, label) {
  return `${matchId}|${label}`
}

export const useComboStore = defineStore('combo', {
  state: () => ({ ...load(), open: false, justSaved: false }),
  getters: {
    has: (state) => (key) => state.legs.some((l) => l.key === key),
    count: (state) => state.legs.length
  },
  actions: {
    save() {
      try {
        localStorage.setItem(KEY, JSON.stringify({ legs: this.legs, amount: this.amount }))
      } catch (e) { /* storage unavailable: the combo just won't survive a reload */ }
    },
    // One leg per match: two picks of the same match depend on each other, and
    // multiplying their probabilities would overstate the chance both come in.
    // Returns the leg already there for that match instead of adding a second one.
    add(leg) {
      const clash = this.legs.find((l) => l.matchId === leg.matchId)
      if (clash && clash.key !== leg.key) return clash
      if (!clash) this.legs.push({ ...leg, myOdds: leg.bestOdds || leg.odds })
      this.justSaved = false
      this.save()
      return null
    },
    replace(leg) {
      this.legs = this.legs.filter((l) => l.matchId !== leg.matchId)
      this.legs.push({ ...leg, myOdds: leg.bestOdds || leg.odds })
      this.save()
    },
    remove(key) {
      this.legs = this.legs.filter((l) => l.key !== key)
      this.save()
    },
    setOdds(key, value) {
      const leg = this.legs.find((l) => l.key === key)
      const v = Number(value)
      if (leg && v > 1) { leg.myOdds = v; this.save() }
    },
    setAmount(value) {
      const v = Number(value)
      if (v > 0) { this.amount = v; this.save() }
    },
    clear() {
      this.legs = []
      this.save()
    }
  }
})

// Numbers of a combo, pure so the panel and the bar agree.
export function comboNumbers(legs, amount) {
  if (!legs.length) return null
  const prob = legs.reduce((x, l) => x * l.probability, 1)
  const odds = legs.reduce((x, l) => x * (l.myOdds || l.odds), 1)
  const bestOdds = legs.reduce((x, l) => x * (l.bestOdds || l.odds), 1)
  return {
    prob,
    odds,
    bestOdds,
    win: amount * (odds - 1),
    lose: amount,
    expected: amount * (prob * odds - 1),
    expectedPct: prob * odds - 1,
    singles: legs.map((l) => ({ key: l.key, expectedPct: l.probability * (l.myOdds || l.odds) - 1 })),
    allTen: prob ** 10
  }
}
