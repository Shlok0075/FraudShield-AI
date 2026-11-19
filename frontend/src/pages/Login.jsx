import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const HIGHLIGHTS = [
  ['Hybrid risk engine', 'ML, anomaly detection, behaviour, rules and graph signals combined into one score.'],
  ['Automated investigation', 'Obvious false alarms clear themselves and obvious fraud is blocked. Analysts see the rest.'],
  ['Explainable decisions', 'Every score comes with the reasons behind it, so nothing is a black box.'],
]

function Eye({ off }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 4l16 16" />}
    </svg>
  )
}

export default function Login() {
  const { login, loading, error, notice, isAuthenticated, restoring } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)

  const destination = location.state?.from || '/dashboard'

  // Already signed in (or a saved session is being checked): don't show the form at all.
  if (restoring) return <div className="min-h-screen grid place-items-center bg-slate-950 text-slate-500">Restoring your session…</div>
  if (isAuthenticated) return <Navigate to={destination} replace />

  async function handleSubmit(e) {
    e.preventDefault()
    if (loading) return
    const ok = await login(email.trim(), password)
    if (ok) navigate(destination, { replace: true })
  }

  const field = 'w-full rounded-lg bg-slate-800/80 border border-slate-700 px-3.5 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30'

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-slate-950">
      <aside className="hidden lg:flex flex-col justify-between p-12 bg-gradient-to-br from-indigo-950 via-slate-950 to-slate-950 border-r border-slate-800">
        <div className="flex items-center gap-3 text-white">
          <span className="text-2xl">🛡️</span>
          <span className="text-lg font-semibold tracking-tight">FraudShield AI</span>
        </div>
        <div className="space-y-8 max-w-md">
          <h2 className="text-3xl font-bold leading-tight text-white">Catch fraud as it happens, and explain every decision.</h2>
          <ul className="space-y-5">
            {HIGHLIGHTS.map(([title, body]) => (
              <li key={title} className="flex gap-3">
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-indigo-400" />
                <div>
                  <p className="text-sm font-medium text-white">{title}</p>
                  <p className="text-sm text-slate-400">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-slate-600">Final-year academic project. All data is synthetic.</p>
      </aside>

      <main className="flex items-center justify-center p-6">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-5">
          <div className="space-y-1">
            <div className="lg:hidden text-3xl">🛡️</div>
            <h1 className="text-2xl font-bold text-white">Sign in</h1>
            <p className="text-sm text-slate-500">Use your analyst or admin account.</p>
          </div>

          {notice && !error && (
            <div role="status" className="text-sm text-amber-300 bg-amber-950/40 border border-amber-900 rounded-lg px-3 py-2">{notice}</div>
          )}
          {error && (
            <div role="alert" className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">{error}</div>
          )}

          <div className="space-y-1.5">
            <label htmlFor="email" className="text-xs font-medium text-slate-400">Email</label>
            <input
              id="email" type="email" required autoFocus autoComplete="username" placeholder="you@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)} className={field}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="text-xs font-medium text-slate-400">Password</label>
            <div className="relative">
              <input
                id="password" type={show ? 'text' : 'password'} required autoComplete="current-password" placeholder="Your password"
                value={password} onChange={(e) => setPassword(e.target.value)} className={`${field} pr-11`}
              />
              <button
                type="button" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide password' : 'Show password'}
                className="absolute inset-y-0 right-0 px-3 text-slate-500 hover:text-slate-200"
              >
                <Eye off={show} />
              </button>
            </div>
          </div>

          <button
            type="submit" disabled={loading || !email || !password}
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 text-sm transition"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-xs text-center text-slate-600">
            Academic prototype. Never enter real card or account data.
          </p>
        </form>
      </main>
    </div>
  )
}
