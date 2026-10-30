/**
 * FraudShield AI - Axios API client (PART 4.11 / Week 9 Day 2)
 * ================================================================
 * Axios instance with baseURL + a JWT interceptor. The token is kept in
 * memory (via authToken.set/get), never in localStorage, to reduce XSS
 * risk -- see docs/security.md for the documented tradeoff (session is
 * lost on page refresh; acceptable for this academic build).
 */
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

let currentToken = null

export const authToken = {
  set: (token) => { currentToken = token },
  get: () => currentToken,
  clear: () => { currentToken = null },
}

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
    if (error.response?.status === 401) {
      authToken.clear()
    }
    return Promise.reject(error)
  }
)

export const API_BASE_URL = API_URL
export default api
