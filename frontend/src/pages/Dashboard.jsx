/**
 * FraudShield AI - Dashboard page (Week 9-11)
 * =============================================
 * Live KPI cards, trend/risk-distribution charts (Recharts), recent
 * transactions table, and real-time updates via Socket.IO
 * (new_transaction / new_alert events -- no polling, Week 11 Day 2).
 *
 * Every figure on this page is LIVE pipeline traffic and starts at zero. The
 * PaySim corpus (6.36M rows) is training data, not live volume, so it lives in
 * its own labelled panel and behind /dashboard/corpus-trends.
 */
import { useEffect, useState, useCallback } from 'react'
import {
  LineChart, Line, PieChart, Pie, Cell, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import api from '../services/api'
import { getSocket } from '../services/socket'
import KpiCard from '../components/KpiCard'
import RiskBadge from '../components/RiskBadge'
import { Link } from 'react-router-dom'

const RISK_COLORS = { LOW: '#4ade80', MEDIUM: '#facc15', HIGH: '#fb923c', CRITICAL: '#f87171' }

const int = (n) => (typeof n === 'number' ? n.toLocaleString() : n)
const pct = (n, d = 3) => (typeof n === 'number' ? n.toFixed(d) : n)

export default function Dashboard() {
  const [kpis, setKpis] = useState(null)
  const [trends, setTrends] = useState([])
  const [riskDist, setRiskDist] = useState([])
  const [geographic, setGeographic] = useState([])
  const [modelInfo, setModelInfo] = useState(null)
  const [feed, setFeed] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [liveEvents, setLiveEvents] = useState([])
  const [error, setError] = useState(null)

  const loadAll = useCallback(async () => {
    // Hourly buckets: at 3 txns every 5s a day-granularity chart is a single
    // point for most of the first hour, which reads as "broken" rather than
    // "quiet". allSettled so one slow panel can't blank the page again.
    const reqs = [
      ['/dashboard/kpis', setKpis],
      ['/dashboard/trends?granularity=hour', (d) => setTrends(d.series)],
      ['/dashboard/risk-distribution', setRiskDist],
      ['/dashboard/geographic', setGeographic],
      ['/dashboard/model-info', setModelInfo],
      ['/monitoring/live-feed', setFeed],
      ['/transactions?page_size=10', (d) => setTransactions(d.items)],
    ]
    const res = await Promise.allSettled(reqs.map(([p]) => api.get(p)))
    const bad = []
    res.forEach((r, i) => {
      if (r.status === 'fulfilled') reqs[i][1](r.value.data)
      else bad.push(reqs[i][0])
    })
    setError(bad.length ? bad.join(', ') : null)
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  useEffect(() => {
    const socket = getSocket()
    const onNewTransaction = (payload) => {
      setLiveEvents((prev) => [{ type: 'transaction', ...payload }, ...prev].slice(0, 8))
      loadAll()
    }
    const onNewAlert = (payload) => {
      setLiveEvents((prev) => [{ type: 'alert', ...payload }, ...prev].slice(0, 8))
    }
    socket.on('new_transaction', onNewTransaction)
    socket.on('new_alert', onNewAlert)
    return () => {
      socket.off('new_transaction', onNewTransaction)
      socket.off('new_alert', onNewAlert)
    }
  }, [loadAll])

  if (!kpis) return <div className="p-8 text-slate-400">Loading dashboard…</div>

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
            feed?.running
              ? 'border-emerald-700/60 bg-emerald-950/40 text-emerald-300'
              : 'border-amber-700/60 bg-amber-950/40 text-amber-300'
          }`}
        >
          <span className={`h-2 w-2 rounded-full ${feed?.running ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
          {feed?.running ? 'LIVE FEED RUNNING' : feed?.enabled === false ? 'LIVE FEED DISABLED' : 'LIVE FEED STOPPED'}
        </span>
        {feed?.running && (
          <span className="text-xs text-slate-500">
            {feed.burst_size} txn every {feed.interval_seconds}s · {int(feed.generated)} generated
            {feed.errors > 0 && <span className="text-rose-400"> · {feed.errors} errors</span>}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-amber-700/60 bg-amber-950/30 px-4 py-2 text-sm text-amber-300">
          Could not load: {error}. The remaining panels are still live.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <KpiCard label="Total Transactions" value={int(kpis.total_transactions)} />
        <KpiCard label="Fraud (Critical)" value={int(kpis.fraud_count)} accent="risk-critical" />
        <KpiCard label="Suspicious" value={int(kpis.suspicious_count)} accent="risk-medium" />
        <KpiCard label="Safe" value={int(kpis.safe_count)} accent="risk-low" />
        <KpiCard label="Fraud Rate" value={`${(kpis.fraud_rate * 100).toFixed(2)}%`} />
        <KpiCard label="Active Alerts" value={int(kpis.active_alerts)} accent="risk-high" />
        <KpiCard label="High-Risk Users" value={int(kpis.high_risk_users)} />
      </div>

      {modelInfo && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap gap-6 text-sm">
          <span className="text-slate-500">Model: <span className="text-white font-medium">{modelInfo.version}</span></span>
          <span className="text-slate-500">
            Review precision: <span className="text-white">{pct(modelInfo.precision)}</span>
          </span>
          <span className="text-slate-500">
            Review recall: <span className="text-white">{pct(modelInfo.recall)}</span>
          </span>
          <span className="text-slate-500">
            Review F1: <span className="text-white">{pct(modelInfo.f1)}</span>
          </span>
          <span className="text-slate-500">
            Block precision: <span className="text-white">{pct(modelInfo.block_precision)}</span>
          </span>
          <span className="text-slate-500">
            Block recall: <span className="text-white">{pct(modelInfo.block_recall)}</span>
          </span>
          <span className="text-slate-500">
            Block F1: <span className="text-white">{pct(modelInfo.block_f1)}</span>
          </span>
          <span className="text-slate-500">ROC-AUC: <span className="text-white">{pct(modelInfo.roc_auc, 4)}</span></span>
          <span className="text-slate-500">PR-AUC: <span className="text-white">{pct(modelInfo.pr_auc, 4)}</span></span>
          <span className="text-slate-500">Predictions served: <span className="text-white">{int(modelInfo.predictions_served)}</span></span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Live Transactions & Fraud (hourly)</h3>
          {trends.length === 0 ? (
            <div className="h-[220px] flex items-center justify-center text-sm text-slate-500">
              Waiting for the first live transactions…
            </div>
          ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="bucket" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }} />
              <Legend />
              <Line type="monotone" dataKey="transactions" stroke="#818cf8" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="fraud" stroke="#f87171" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
          )}
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Risk Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={riskDist} dataKey="value" nameKey="label" innerRadius={45} outerRadius={80}>
                {riskDist.map((entry) => (
                  <Cell key={entry.label} fill={RISK_COLORS[entry.label] || '#64748b'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Transactions by Location</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={geographic}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="label" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b' }} />
              <Bar dataKey="value" fill="#818cf8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Recent Transactions</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-800">
                <th className="py-2">ID</th><th>Amount</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id} className="border-b border-slate-800/60">
                  <td className="py-2">{t.id}</td>
                  <td>{t.currency} {t.amount}</td>
                  <td className="capitalize">{t.status}</td>
                  <td>
                    <Link to={`/transactions/${t.id}`} className="text-indigo-400 hover:underline text-xs">
                      Investigate →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {liveEvents.length > 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Live Feed (WebSocket)</h3>
          <div className="space-y-1 text-sm">
            {liveEvents.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-slate-400">
                <span className="text-xs text-slate-600">{e.type === 'alert' ? 'ALERT' : 'TXN'}</span>
                <span>#{e.transaction_id}</span>
                {e.risk_level && <RiskBadge level={e.risk_level} />}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-sm text-slate-500">
          Live feed connected — waiting for the next transaction.
        </div>
      )}

      {kpis.paysim_total > 0 && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-400 mb-1">
            Training corpus (PaySim) — not live volume
          </h3>
          <p className="text-xs text-slate-600 mb-3">
            Historical data used to train the model. Excluded from the KPIs above, which
            count only live pipeline traffic. Full series at <code>/dashboard/corpus-trends</code>.
          </p>
          <div className="flex flex-wrap gap-6 text-sm">
            <span className="text-slate-500">
              Rows: <span className="text-slate-300">{int(kpis.paysim_total)}</span>
            </span>
            <span className="text-slate-500">
              Fraud: <span className="text-slate-300">{int(kpis.paysim_fraud)}</span>
            </span>
            <span className="text-slate-500">
              Rate: <span className="text-slate-300">{pct(kpis.paysim_fraud_rate * 100, 4)}%</span>
            </span>
            <span className="text-slate-500">
              Users: <span className="text-slate-300">{int(kpis.paysim_users)}</span>
            </span>
            <span className="text-slate-500">
              Counterparties: <span className="text-slate-300">{int(kpis.paysim_counterparties)}</span>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
