import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login, loading, error } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('admin@fraudshield.ai')
  const [password, setPassword] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    const ok = await login(email, password)
    if (ok) navigate('/dashboard')
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <form onSubmit={handleSubmit} className="w-full max-w-sm bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-5">
        <div className="text-center space-y-1">
          <div className="text-3xl">🛡️</div>
          <h1 className="text-xl font-bold text-white">FraudShield AI</h1>
          <p className="text-sm text-slate-500">Academic prototype — sign in to continue</p>
        </div>

        {error && (
          <div className="text-sm text-red-400 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="text-xs text-slate-400">Email</label>
          <input
            type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-slate-400">Password</label>
          <input
            type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
          />
        </div>

        <button
          type="submit" disabled={loading}
          className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 text-sm"
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="text-xs text-center text-slate-600">
          Public/synthetic academic prototype. Never use real card data.
        </p>
      </form>
    </div>
  )
}
