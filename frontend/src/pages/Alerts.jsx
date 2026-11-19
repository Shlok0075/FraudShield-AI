/**
 * FraudShield AI - Alerts page (Week 10 Day 4 / Week 12)
 * =========================================================
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import { getSocket } from '../services/socket'
import RiskBadge from '../components/RiskBadge'

const STATUS_OPTIONS = ['open', 'reviewed', 'false_positive', 'escalated', 'resolved']

const PAGE_SIZE = 100          // rows fetched per request (server max is 500)
const REFRESH_MIN_MS = 3000    // coalesce bursts of socket events into one reload

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadedCount = useRef(0)
  const refreshTimer = useRef(null)

  const filterParams = () => (statusFilter ? { status_filter: statusFilter } : {})

  // Reload what the user already has on screen (at least one page), not the whole table.
  async function load() {
    const limit = Math.min(500, Math.max(PAGE_SIZE, loadedCount.current))
    const { data } = await api.get('/alerts', { params: { ...filterParams(), limit, offset: 0 } })
    loadedCount.current = data.length
    setAlerts(data)
    setHasMore(data.length === limit)
  }

  async function loadMore() {
    setLoadingMore(true)
    try {
      const { data } = await api.get('/alerts', {
        params: { ...filterParams(), limit: PAGE_SIZE, offset: loadedCount.current },
      })
      loadedCount.current += data.length
      setAlerts((prev) => [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => { loadedCount.current = 0; load() }, [statusFilter])

  useEffect(() => {
    const socket = getSocket()
    // The feed raises alerts continuously; reloading on every event hammered the API.
    const refresh = () => {
      if (refreshTimer.current) return
      refreshTimer.current = setTimeout(() => { refreshTimer.current = null; load() }, REFRESH_MIN_MS)
    }
    socket.on('new_alert', refresh)
    socket.on('alert_updated', refresh)
    return () => {
      socket.off('new_alert', refresh)
      socket.off('alert_updated', refresh)
      if (refreshTimer.current) { clearTimeout(refreshTimer.current); refreshTimer.current = null }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  async function updateStatus(id, status) {
    await api.patch(`/alerts/${id}`, { status })
    load()
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-white">Fraud Alerts</h1>
        <select
          value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg text-sm px-3 py-1.5 text-white"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 bg-slate-950/50">
              <th className="py-2 px-4">Alert</th>
              <th className="px-4">Transaction</th>
              <th className="px-4">Severity</th>
              <th className="px-4">Status</th>
              <th className="px-4">Created</th>
              <th className="px-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id} className="border-t border-slate-800">
                <td className="py-2 px-4">#{a.id}</td>
                <td className="px-4">
                  <Link to={`/transactions/${a.transaction_id}`} className="text-indigo-400 hover:underline">
                    #{a.transaction_id}
                  </Link>
                </td>
                <td className="px-4"><RiskBadge level={a.severity} /></td>
                <td className="px-4 capitalize">{a.status.replace('_', ' ')}</td>
                <td className="px-4 text-slate-500">{new Date(a.created_at).toLocaleString()}</td>
                <td className="px-4 space-x-2">
                  {a.status === 'open' && (
                    <>
                      <button onClick={() => updateStatus(a.id, 'reviewed')} className="text-xs text-indigo-400 hover:underline">Review</button>
                      <button onClick={() => updateStatus(a.id, 'false_positive')} className="text-xs text-slate-400 hover:underline">False Positive</button>
                      <button onClick={() => updateStatus(a.id, 'resolved')} className="text-xs text-green-400 hover:underline">Resolve</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-slate-500">No alerts.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <div className="text-center">
          <button onClick={loadMore} disabled={loadingMore}
                  className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-white hover:bg-slate-700 disabled:opacity-50">
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
