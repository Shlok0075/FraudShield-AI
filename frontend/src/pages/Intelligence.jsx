/**
 * FraudShield AI - AI Intelligence & Monitoring
 * Drift, model registry, security checks, merchant risk and behavioural profiles. Each panel loads
 * independently, so one slow or failing endpoint never blanks the rest of the page.
 */
import { useCallback, useEffect, useState } from 'react'
import api from '../services/api'

const PANELS = [
  ['drift', 'Drift', '/monitoring/drift'],
  ['models', 'Model registry', '/monitoring/models'],
  ['security', 'Security', '/monitoring/security'],
  ['merchants', 'Merchant risk', '/merchants'],
  ['profiles', 'Behavioural profiles', '/profiles'],
]

const DRIFT_TONE = { NORMAL: 'text-emerald-400', WARNING: 'text-yellow-400', CRITICAL: 'text-red-400' }
const riskTone = (s) => (s >= 60 ? 'bg-red-500' : s >= 30 ? 'bg-yellow-500' : 'bg-emerald-500')
const money = (v) => `₹${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
const pct = (v, d = 1) => `${(Number(v || 0) * 100).toFixed(d)}%`

function Card({ title, children, className = '', right }) {
  return (
    <section className={`bg-slate-900 border border-slate-800 rounded-xl p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-white font-semibold">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

const Skeleton = () => <div className="h-16 rounded bg-slate-800/60 animate-pulse" />
const Empty = ({ children }) => <p className="text-sm text-slate-500">{children}</p>

export default function Intelligence() {
  const [data, setData] = useState({})        // key -> response
  const [state, setState] = useState({})      // key -> 'loading' | 'ok' | 'error'
  const [updated, setUpdated] = useState(null)

  const load = useCallback(() => {
    setState(Object.fromEntries(PANELS.map(([k]) => [k, 'loading'])))
    // Independent requests: each panel fills in as soon as its own call returns.
    PANELS.forEach(([key, , url]) => {
      api.get(url)
        .then((r) => { setData((d) => ({ ...d, [key]: r.data })); setState((s) => ({ ...s, [key]: 'ok' })); setUpdated(new Date()) })
        .catch(() => setState((s) => ({ ...s, [key]: 'error' })))
    })
  }, [])

  useEffect(() => { load() }, [load])

  const failed = PANELS.filter(([k]) => state[k] === 'error').map(([, t]) => t)
  const busy = (k) => state[k] === 'loading' && data[k] === undefined
  const { drift, models = [], security = [], merchants = [], profiles = [] } = data
  const passing = security.filter((x) => x.status === 'PASS').length
  const active = models.find((m) => m.is_active) || models.find((m) => m.status === 'active')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-white">AI Intelligence &amp; Monitoring</h1>
          <p className="text-sm text-slate-500">Model health, merchant risk and customer behaviour, computed from live traffic.</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          {updated && <span>Updated {updated.toLocaleTimeString()}</span>}
          <button onClick={load} className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm">Refresh</button>
        </div>
      </div>

      {failed.length > 0 && (
        <div className="rounded-xl border border-amber-700/60 bg-amber-950/30 px-4 py-2 text-sm text-amber-300">
          Could not load: {failed.join(', ')}. The other panels are still live.
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-4">
        <Card title="Prediction drift">
          {busy('drift') ? <Skeleton /> : drift ? (
            <>
              <div className={`text-2xl font-semibold ${DRIFT_TONE[drift.status] || 'text-white'}`}>{drift.status?.replace('_', ' ') || '—'}</div>
              <p className="text-sm text-slate-500">
                {drift.status === 'INSUFFICIENT_DATA'
                  ? `${drift.samples} predictions so far. Needs at least 20.`
                  : `PSI ${Number(drift.psi).toFixed(4)} over ${drift.samples.toLocaleString()} predictions`}
              </p>
              <p className="text-xs text-slate-600 mt-1">Under 0.10 is stable, 0.10 to 0.25 is a warning, above that is drift.</p>
            </>
          ) : <Empty>No data.</Empty>}
        </Card>

        <Card title="Model registry">
          {busy('models') ? <Skeleton /> : (
            <>
              <p className="text-2xl text-white">{models.length}</p>
              <p className="text-sm text-slate-500">registered version{models.length === 1 ? '' : 's'}</p>
              {active && <p className="text-xs text-slate-400 mt-1">Active: {active.version}{active.pr_auc != null ? ` · PR-AUC ${Number(active.pr_auc).toFixed(3)}` : ''}</p>}
            </>
          )}
        </Card>

        <Card title="Security controls">
          {busy('security') ? <Skeleton /> : (
            <>
              <p className="text-2xl text-white">{passing}/{security.length}</p>
              <p className="text-sm text-slate-500">checks passing</p>
              {security.some((x) => x.status !== 'PASS') && (
                <p className="text-xs text-amber-400 mt-1">Failing: {security.filter((x) => x.status !== 'PASS').map((x) => x.check_name).join(', ')}</p>
              )}
            </>
          )}
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Merchant risk" right={<span className="text-xs text-slate-500">share of HIGH or CRITICAL transactions</span>}>
          {busy('merchants') ? <Skeleton /> : merchants.length === 0 ? (
            <Empty>No merchant activity yet. Merchants appear once transactions reference them.</Empty>
          ) : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-slate-500 text-xs"><th className="pb-2">Merchant</th><th>Txns</th><th>Risky</th><th className="w-32">Risk</th></tr></thead>
              <tbody>
                {merchants.slice(0, 10).map((m) => (
                  <tr key={m.id} className="border-t border-slate-800">
                    <td className="py-2 text-slate-200">{m.name}</td>
                    <td className="text-slate-400">{m.transactions.toLocaleString()}</td>
                    <td className="text-slate-400">{pct(m.fraud_rate)}</td>
                    <td>
                      <div className="h-1.5 rounded bg-slate-800"><div className={`h-full rounded ${riskTone(m.risk_score)}`} style={{ width: `${Math.min(100, m.risk_score)}%` }} /></div>
                      <span className="text-xs text-slate-500">{Math.round(m.risk_score)}/100</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Behavioural profiles" right={<span className="text-xs text-slate-500">most active customers</span>}>
          {busy('profiles') ? <Skeleton /> : profiles.length === 0 ? (
            <Empty>No customer activity yet.</Empty>
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-slate-500 text-xs"><th className="pb-2">Customer</th><th>Txns</th><th>Avg</th><th>Max</th><th>Risky</th></tr></thead>
                <tbody>
                  {profiles.map((p) => (
                    <tr key={p.user_id} className="border-t border-slate-800">
                      <td className="py-2 text-slate-200">User {p.user_id}</td>
                      <td className="text-slate-400">{p.transaction_count.toLocaleString()}</td>
                      <td className="text-slate-400">{money(p.avg_amount)}</td>
                      <td className="text-slate-400">{money(p.max_amount)}</td>
                      <td className={p.fraud_rate >= 0.1 ? 'text-red-400' : 'text-slate-400'}>{pct(p.fraud_rate, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
