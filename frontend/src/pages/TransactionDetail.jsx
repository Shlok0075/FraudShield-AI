/**
 * FraudShield AI - Transaction Investigation page (Week 12 Day 1-2)
 * =====================================================================
 * "Fraud Risk: 87% — HIGH — Main Reasons: ..." explanation panel plus the AUTOMATED outcome
 * (allowed / cleared / blocked / waiting for an analyst). Nobody sets a status by hand: the
 * system already decided, and a person is only asked where one is needed.
 */
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import RiskBadge from '../components/RiskBadge'
import { useAuth } from '../context/AuthContext'

const TONE = {
  allowed: 'border-emerald-800 bg-emerald-950/30 text-emerald-300',
  cleared: 'border-emerald-800 bg-emerald-950/30 text-emerald-300',
  blocked: 'border-red-800 bg-red-950/30 text-red-300',
  review: 'border-yellow-800 bg-yellow-950/30 text-yellow-300',
  pending: 'border-slate-700 bg-slate-900 text-slate-300',
  closed: 'border-slate-700 bg-slate-900 text-slate-300',
}
// Decisions that only record a human sign-off; the server closes and assigns the case itself.
const DECISIONS = {
  blocked: [['confirmed_fraud', 'Confirm fraud', 'bg-red-700 hover:bg-red-600'], ['false_positive', 'Overturn: legitimate', 'bg-slate-700 hover:bg-slate-600']],
  review: [['confirmed_fraud', 'Confirm fraud', 'bg-red-700 hover:bg-red-600'], ['false_positive', 'Mark legitimate', 'bg-emerald-700 hover:bg-emerald-600']],
  cleared: [['false_positive', 'Agree: legitimate', 'bg-emerald-700 hover:bg-emerald-600'], ['confirmed_fraud', 'Wrong: this is fraud', 'bg-red-700 hover:bg-red-600']],
}

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

  async function decide(caseId, decision) {
    await api.patch(`/cases/${caseId}`, { decision })
    setToast(decision === 'confirmed_fraud' ? 'Recorded as confirmed fraud.' : 'Recorded as legitimate.')
    load()
    setTimeout(() => setToast(null), 2500)
  }

  if (!detail) return <div className="p-8 text-slate-400">Loading…</div>

  const { transaction, prediction, related_transactions, outcome } = detail
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
              Model version: {prediction.model_version}. The system decides automatically; a person confirms blocked transactions.
            </p>
          </div>
        )}

        {outcome && (
          <div className={`rounded-xl border p-4 space-y-2 ${TONE[outcome.state] || TONE.pending}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold">{outcome.label}</span>
              {outcome.investigation?.confidence != null && (
                <span className="text-xs opacity-80">Confidence {outcome.investigation.confidence}% · {outcome.investigation.risk_level}</span>
              )}
            </div>
            <p className="text-xs opacity-80">{outcome.detail}</p>
            {outcome.investigation?.checks?.length > 0 && (
              <ul className="text-xs list-disc pl-4 opacity-90">
                {outcome.investigation.checks.map((c) => <li key={c}>{c}</li>)}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {canAct && outcome.can_decide && (DECISIONS[outcome.state] || []).map(([d, label, tone]) => (
                <button key={d} onClick={() => decide(outcome.case_id, d)} className={`px-3 py-1.5 rounded-lg text-xs font-medium text-white ${tone}`}>{label}</button>
              ))}
              {outcome.case_id != null && (
                <Link to="/cases" className="text-xs text-indigo-300 hover:underline">Open case #{outcome.case_id}</Link>
              )}
            </div>
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
