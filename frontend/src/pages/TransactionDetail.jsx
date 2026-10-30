/**
 * FraudShield AI - Transaction Investigation page (Week 12 Day 1-2)
 * =====================================================================
 * "Fraud Risk: 87% — HIGH — Main Reasons: ..." explanation panel + admin
 * actions (mark_reviewed / mark_false_positive / escalate / resolve).
 */
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import RiskBadge from '../components/RiskBadge'
import { useAuth } from '../context/AuthContext'

const ACTIONS = [
  { key: 'mark_reviewed', label: 'Mark Reviewed' },
  { key: 'mark_false_positive', label: 'False Positive' },
  { key: 'escalate', label: 'Escalate' },
  { key: 'resolve', label: 'Resolve' },
]

export default function TransactionDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const [detail, setDetail] = useState(null)
  const [toast, setToast] = useState(null)

  async function load() {
    const { data } = await api.get(`/transactions/${id}/detail`)
    setDetail(data)
  }

  useEffect(() => { load() }, [id])

  async function runAction(action) {
    await api.patch(`/transactions/${id}/action`, { action })
    setToast(`Action "${action}" applied.`)
    load()
    setTimeout(() => setToast(null), 2500)
  }

  if (!detail) return <div className="p-8 text-slate-400">Loading…</div>

  const { transaction, prediction, related_transactions } = detail
  const canAct = user?.role === 'admin' || user?.role === 'analyst'

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      <Link to="/dashboard" className="text-sm text-indigo-400 hover:underline">← Back to Dashboard</Link>

      {toast && <div className="bg-green-950/40 border border-green-800 text-green-300 text-sm rounded-lg px-4 py-2">{toast}</div>}

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold text-white">Transaction #{transaction.id}</h1>
          {prediction && <RiskBadge level={prediction.risk_level} />}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div><span className="text-slate-500">Amount</span><div className="text-white font-medium">{transaction.currency} {transaction.amount}</div></div>
          <div><span className="text-slate-500">Status</span><div className="text-white font-medium capitalize">{transaction.status}</div></div>
          <div><span className="text-slate-500">Payment Method</span><div className="text-white font-medium">{transaction.payment_method || '—'}</div></div>
          <div><span className="text-slate-500">Location</span><div className="text-white font-medium">{transaction.location || '—'}</div></div>
        </div>

        {prediction && (
          <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-2">
            <div className="text-sm text-slate-300">
              Fraud Risk: <span className="font-bold text-white">{Math.round(prediction.probability * 100)}%</span>
              {' — '}<span className="font-bold">{prediction.risk_level}</span>
            </div>
            <div className="text-xs text-slate-500 uppercase tracking-wide">Main Reasons (SHAP-based, model-derived — not proof of fraud)</div>
            <ul className="space-y-1 text-sm">
              {(prediction.explanation || []).map((item, i) => (
                <li key={i} className="flex justify-between text-slate-300">
                  <span>{item.label}</span>
                  <span className={item.direction === 'increases_risk' ? 'risk-critical' : 'risk-low'}>
                    {item.direction === 'increases_risk' ? '↑' : '↓'} {item.impact}
                  </span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-slate-600 pt-1">
              Model version: {prediction.model_version}. A human must review before any real action is taken.
            </p>
          </div>
        )}

        {canAct && (
          <div className="flex gap-2 flex-wrap">
            {ACTIONS.map((a) => (
              <button
                key={a.key} onClick={() => runAction(a.key)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-2">Related Transactions (Same User)</h3>
        {related_transactions.length === 0 ? (
          <p className="text-sm text-slate-500">No other transactions for this user yet.</p>
        ) : (
          <ul className="text-sm space-y-1">
            {related_transactions.map((t) => (
              <li key={t.id} className="flex justify-between text-slate-400">
                <Link to={`/transactions/${t.id}`} className="text-indigo-400 hover:underline">#{t.id}</Link>
                <span>{t.currency} {t.amount}</span>
                <span className="capitalize">{t.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
