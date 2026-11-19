/**
 * FraudShield AI - Audit Log viewer, Admin-only (Week 12 Day 5)
 * =================================================================
 * Shows the account that performed each action (by email, not a raw id), the
 * resolved target, and the event detail. Failed logins are recorded too and
 * highlighted -- they are the rows an investigator is actually looking for.
 */
import { useEffect, useState } from 'react'
import api from '../services/api'

const PAGE_SIZE = 20

export default function AuditLog() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [actions, setActions] = useState([])
  const [action, setAction] = useState('')
  const [onlyAuth, setOnlyAuth] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)

  // The list of action names is loaded once, not re-queried on every page turn.
  useEffect(() => { api.get('/audit/actions').then(({ data }) => setActions(data)).catch(() => {}) }, [])

  useEffect(() => {
    let live = true
    setLoading(true)
    api.get('/audit', {
      params: { page, page_size: PAGE_SIZE, action: onlyAuth ? 'auth*' : action || undefined },
    }).then(({ data }) => {
      if (!live) return
      setItems(data.items); setTotal(data.total); setError(null)
    }).catch(() => { if (live) setError('Could not load the audit log.') })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [page, action, onlyAuth, tick])

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // Any filter change invalidates the current page number.
  const setFilter = (fn) => { fn(); setPage(1) }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <h1 className="text-lg font-bold text-white">
        Audit Log <span className="text-sm text-slate-500">({total.toLocaleString()} entries)</span>
      </h1>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          onClick={() => setFilter(() => setOnlyAuth((v) => !v))}
          className={`px-3 py-1 rounded border ${
            onlyAuth
              ? 'border-indigo-500 bg-indigo-950/60 text-indigo-200'
              : 'border-slate-700 bg-slate-900 text-slate-400 hover:border-slate-600'
          }`}
        >
          Auth events only
        </button>
        <select
          value={action}
          disabled={onlyAuth}
          onChange={(e) => setFilter(() => setAction(e.target.value))}
          className="px-3 py-1 rounded bg-slate-900 border border-slate-700 text-slate-300 disabled:opacity-40"
        >
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <button onClick={() => setTick((t) => t + 1)} className="px-3 py-1 rounded border border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {error && <div role="alert" className="text-sm text-red-300 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">{error}</div>}

      <div className={`bg-slate-900 border border-slate-800 rounded-xl overflow-hidden transition-opacity ${loading ? 'opacity-60' : ''}`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 bg-slate-950/50">
              <th className="py-2 px-4">Actor</th>
              <th className="px-4">Action</th>
              <th className="px-4">Target</th>
              <th className="px-4">Detail</th>
              <th className="px-4">IP</th>
              <th className="px-4">When</th>
            </tr>
          </thead>
          <tbody>
            {items.map((log) => {
              const failed = log.action === 'auth.login_failed'
              return (
                <tr key={log.id} className={`border-t border-slate-800 ${failed ? 'bg-rose-950/25' : ''}`}>
                  <td className="py-2 px-4">
                    <div className="text-slate-300">{log.user_email || '—'}</div>
                    {log.user_id != null && (
                      <div className="text-xs text-slate-600">id {log.user_id}</div>
                    )}
                  </td>
                  <td className={`px-4 font-mono text-xs ${failed ? 'text-rose-300' : 'text-slate-300'}`}>
                    {log.action}
                  </td>
                  <td className="px-4 text-slate-400">{log.target_label || '—'}</td>
                  <td className="px-4 text-slate-500 text-xs">{log.detail || '—'}</td>
                  <td className="px-4 text-slate-500">{log.ip_address || '—'}</td>
                  <td className="px-4 text-slate-500 whitespace-nowrap">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                </tr>
              )
            })}
            {items.length === 0 && !loading && (
              <tr><td colSpan={6} className="py-6 px-4 text-center text-slate-500">No entries match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end items-center gap-2 text-sm">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
          className="px-3 py-1 rounded bg-slate-800 disabled:opacity-40">Prev</button>
        <span className="text-slate-500">{total === 0 && loading ? "Loading…" : `Page ${page} of ${pages}`}</span>
        <button disabled={page >= pages} onClick={() => setPage((p) => p + 1)}
          className="px-3 py-1 rounded bg-slate-800 disabled:opacity-40">Next</button>
      </div>
    </div>
  )
}
