/**
 * FraudShield AI - Alerts page (Week 10 Day 4 / Week 12)
 * =========================================================
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../services/api'
import { getSocket } from '../services/socket'
import RiskBadge from '../components/RiskBadge'

const STATUS_OPTIONS = ['open', 'reviewed', 'false_positive', 'escalated', 'resolved']

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [statusFilter, setStatusFilter] = useState('')

  async function load() {
    const { data } = await api.get('/alerts', { params: statusFilter ? { status_filter: statusFilter } : {} })
    setAlerts(data)
  }

  useEffect(() => { load() }, [statusFilter])

  useEffect(() => {
    const socket = getSocket()
    const refresh = () => load()
    socket.on('new_alert', refresh)
    socket.on('alert_updated', refresh)
    return () => {
      socket.off('new_alert', refresh)
      socket.off('alert_updated', refresh)
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
    </div>
  )
}
