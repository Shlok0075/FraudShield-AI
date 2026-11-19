/**
 * FraudShield AI - Auth context (PART 4.11 / Week 9 Day 2)
 * ===========================================================
 * Login/logout, stores the JWT in memory + React state, decodes role
 * from the token (a plain base64 decode of the JWT payload -- no signing
 * verification client-side; the backend is the source of truth).
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import api, { authToken, API_BASE_URL, UNAUTHORIZED_EVENT } from '../services/api'

const AuthContext = createContext(null)

function decodeRole(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role || null
  } catch {
    return null
  }
}

/** A message a person can act on, instead of a bare "Login failed". */
function describeLoginError(err) {
  if (!err.response) {
    const onLocalhost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
    const apiIsLocal = /localhost|127\.0\.0\.1/.test(API_BASE_URL)
    return !onLocalhost && apiIsLocal
      ? `This site is trying to reach ${API_BASE_URL}, which only exists on your own computer. Set VITE_API_URL to the deployed backend address and rebuild.`
      : `Can't reach the server at ${API_BASE_URL}. Check that the backend is running and that CORS allows this site.`
  }
  const status = err.response.status
  if (status === 401) return 'Invalid email or password.'
  if (status === 429) return 'Too many sign-in attempts. Wait a minute and try again.'
  if (status === 422) return 'Enter a valid email address and password.'
  if (status >= 500) return 'The server had a problem. Try again in a moment.'
  return err.response.data?.error?.message || 'Sign-in failed.'
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  // True while a saved session is being checked, so protected pages wait instead of bouncing to /login.
  const [restoring, setRestoring] = useState(() => !!authToken.get())

  useEffect(() => {
    let live = true
    if (authToken.get()) {
      api.get('/auth/me')
        .then((me) => { if (live) setUser(me.data) })
        .catch(() => { authToken.clear() })
        .finally(() => { if (live) setRestoring(false) })
    }
    const expired = () => { setUser(null); setNotice('Your session expired. Please sign in again.') }
    window.addEventListener(UNAUTHORIZED_EVENT, expired)
    return () => { live = false; window.removeEventListener(UNAUTHORIZED_EVENT, expired) }
  }, [])

  const login = useCallback(async (email, password) => {
    setLoading(true)
    setError(null)
    setNotice(null)
    try {
      const { data } = await api.post('/auth/login', { email, password })
      authToken.set(data.access_token)
      const me = await api.get('/auth/me')
      setUser(me.data)
      return true
    } catch (err) {
      setError(describeLoginError(err))
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    authToken.clear()
    setUser(null)
  }, [])

  const isAuthenticated = !!user

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, error, notice, restoring, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
