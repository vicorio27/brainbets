import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// --- GET cache ---------------------------------------------------------------
// Going back to a view must not refetch everything: a fresh answer is served
// from memory, identical requests in flight are shared, and if the backend is
// briefly unreachable (a restart, a slow moment) the last good answer is used
// instead of showing "Network Error". The "Actualizar" button calls
// clearApiCache() to force fresh data.
const FRESH_MS = 2 * 60 * 1000
const cache = new Map() // url -> { at, res }
const inflight = new Map() // url -> Promise
const network = axios.getAdapter(api.defaults.adapter)

api.defaults.adapter = async (config) => {
  if ((config.method || 'get').toLowerCase() !== 'get' || config.noCache) return network(config)
  const key = api.getUri(config)
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < FRESH_MS) return { ...hit.res, config }
  if (inflight.has(key)) return { ...(await inflight.get(key)), config }

  const request = network(config)
    .then((res) => {
      if (res.status >= 200 && res.status < 300) cache.set(key, { at: Date.now(), res })
      return res
    })
    .catch((err) => {
      if (hit && !err.response) return { ...hit.res, config } // offline: keep the last good data
      throw err
    })
    .finally(() => inflight.delete(key))
  inflight.set(key, request)
  return request
}

export function clearApiCache() {
  cache.clear()
}

export default api
