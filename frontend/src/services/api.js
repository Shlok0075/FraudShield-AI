/**
 * FraudShield AI - Axios API client
 * ================================================================
 * Axios instance with baseURL + a JWT interceptor. The token lives in sessionStorage so a page
 * refresh keeps you signed in; it is cleared when the tab closes and on logout or a 401. That is
 * a deliberate trade-off against keeping it purely in memory (which logged you out on every
 * reload): sessionStorage is readable by injected scripts, so the app must stay XSS-clean (React
 * escapes output, no dangerouslySetInnerHTML) and tokens are short-lived. See docs/security.md.
 */
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const STORAGE_KEY = 'fraudshield.token'
const store = {
  get: () => { try { return window.sessionStorage.getItem(STORAGE_KEY) } catch { return null } },
  set: (v) => { try { window.sessionStorage.setItem(STORAGE_KEY, v) } catch { /* storage blocked: stay in memory */ } },
  del: () => { try { window.sessionStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ } },
}

let currentToken = store.get()

export const authToken = {
  set: (token) => { currentToken = token; store.set(token) },
  get: () => currentToken,
  clear: () => { currentToken = null; store.del() },
}

export const UNAUTHORIZED_EVENT = 'fraudshield:unauthorized'

export const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
})

api.interceptors.request.use((config) => {
  if (currentToken) {
    config.headers.Authorization = `Bearer ${currentToken}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // A 401 anywhere except the login call itself means the session expired or was revoked.
    if (error.response?.status === 401 && !String(error.config?.url || '').includes('/auth/login')) {
      authToken.clear()
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    return Promise.reject(error)
  }
)

export const API_BASE_URL = API_URL
export default api
