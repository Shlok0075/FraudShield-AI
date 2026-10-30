/**
 * FraudShield AI - Auth context (PART 4.11 / Week 9 Day 2)
 * ===========================================================
 * Login/logout, stores the JWT in memory + React state, decodes role
 * from the token (a plain base64 decode of the JWT payload -- no signing
 * verification client-side; the backend is the source of truth).
 */
import { createContext, useContext, useState, useCallback } from 'react'
import api, { authToken } from '../services/api'

const AuthContext = createContext(null)

function decodeRole(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role || null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const login = useCallback(async (email, password) => {
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.post('/auth/login', { email, password })
      authToken.set(data.access_token)
      const me = await api.get('/auth/me')
      setUser(me.data)
      return true
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Login failed')
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
    <AuthContext.Provider value={{ user, login, logout, loading, error, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
