/**
 * FraudShield AI - Investigation Cases
 * =====================================
 * Escalated cases are sorted into queues so analysts work a short, prioritised list:
 *   Needs review  - the engine could not decide; an analyst must
 *   Auto-blocked  - transaction blocked automatically; confirm or overturn
 *   Auto-cleared  - closed automatically as a false positive (audit sample)
 *   Closed        - decided by a human
 * The server decides which queue a case belongs to and orders the work queues by priority, then age.
 */
import { useEffect, useRef, useState } from 'react'
import api from '../services/api'
import { getSocket } from '../services/socket'
import RiskBadge from '../components/RiskBadge'

const PAGE_SIZE = 100
const REFRESH_MIN_MS = 3000

const QUEUES = [
  { key: 'needs_review', label: 'Needs review', hint: 'Waiting for an analyst, most severe and oldest first.' },
  { key: 'auto_blocked', label: 'Auto-blocked', hint: 'Blocked automatically. Confirm fraud or overturn the block.' },
  { key: 'auto_cleared', label: 'Auto-cleared', hint: 'Closed automatically as false positives. Spot-check a few.' },
  { key: 'closed', label: 'Closed', hint: 'Decided by an analyst.' },
]
const PRIORITIES = ['critical', 'high', 'medium', 'low']

const DECISION_LABEL = {
  auto_cleared: 'Auto-cleared',
  auto_blocked: 'Auto-blocked',
  needs_review: 'Needs review',
  confirmed_fraud: 'Confirmed fraud',
  false_positive: 'False positive',
}
const decisionLabel = (d) => DECISION_LABEL[d] || d || '—'

function age(ts) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(ts + (String(ts).endsWith('Z') ? '' : 'Z')).getTime()) / 60000))
  if (mins < 60) return `${mins}m`
  if (mins < 60 * 48) return `${Math.round(mins / 60)}h`
  return `${Math.round(mins / 1440)}d`
}

const money = (amount, currency) =>
  amount == null ? '—' : `${currency || ''} ${Number(amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}`.trim()

export default function Cases() {
  const [queue, setQueue] = useState('needs_review')
  const [priority, setPriority] = useState('')
  const [counts, setCounts] = useState(null)
  const [cases, setCases] = useState([])
  const [selected, setSelected] = useState(null)
  const [note, setNote] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const loadedCount = useRef(0)
  const refreshTimer = useRef(null)

  const params = () => ({ queue, ...(priority ? { priority } : {}) })

  // Reload what is already on screen (at least one page) plus the tab counts.
  async function load() {
    const limit = Math.min(500, Math.max(PAGE_SIZE, loadedCount.current))
    const [list, q] = await Promise.all([
      api.get('/cases', { params: { ...params(), limit, offset: 0 } }),
      api.get('/cases/queues'),
    ])
    loadedCount.current = list.data.length
    setCases(list.data)
    setHasMore(list.data.length === limit)
    setCounts(q.data)
  }

  async function loadMore() {
    setLoadingMore(true)
    try {
      const { data } = await api.get('/cases', { params: { ...params(), limit: PAGE_SIZE, offset: loadedCount.current } })
      loadedCount.current += data.length
      setCases((prev) => [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => { loadedCount.current = 0; load() }, [queue, priority])

  // New escalations and automatic decisions appear without a manual refresh (coalesced).
  useEffect(() => {
    const socket = getSocket()
    const refresh = () => {
      if (refreshTimer.current) return
      refreshTimer.current = setTimeout(() => { refreshTimer.current = null; load() }, REFRESH_MIN_MS)
    }
    socket.on('investigation_complete', refresh)
    socket.on('alert_updated', refresh)
    return () => {
      socket.off('investigation_complete', refresh)
      socket.off('alert_updated', refresh)
      if (refreshTimer.current) { clearTimeout(refreshTimer.current); refreshTimer.current = null }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, priority])

  async function reselect(id) {
    const { data } = await api.get(`/cases/${id}`)
    setSelected(data)
  }
  async function update(id, body) {
    await api.patch(`/cases/${id}`, body)
    await load()
    if (selected?.id === id) await reselect(id)
  }
  async function addNote() {
    if (!note.trim()) return
    await api.post(`/cases/${selected.id}/notes`, { note })
    setNote('')
    await reselect(selected.id)
    load()
  }

  const current = QUEUES.find((q) => q.key === queue)
  const mix = counts?.queues?.[queue]?.by_priority

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white">Investigation Cases</h1>
        <p className="text-sm text-slate-500">
          Escalated cases are sorted into queues automatically.
          {counts && <> <span className="text-slate-300">{counts.needs_attention}</span> need an analyst.</>}
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist">
        {QUEUES.map((q) => {
          const n = counts?.queues?.[q.key]?.count
          const active = q.key === queue
          return (
            <button
              key={q.key} role="tab" aria-selected={active}
              onClick={() => { setQueue(q.key); setPriority(''); setSelected(null) }}
              className={`px-4 py-2 rounded-lg border text-sm transition ${
                active ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800'
              }`}
            >
              {q.label}
              {n != null && (
                <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${active ? 'bg-indigo-500/60' : 'bg-slate-800 text-slate-400'}`}>
                  {n.toLocaleString()}
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-500 mr-1">{current.hint}</span>
        <button
          onClick={() => setPriority('')}
          className={`px-2.5 py-1 rounded-full border ${!priority ? 'bg-slate-700 border-slate-500 text-white' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}
        >
          All priorities
        </button>
        {PRIORITIES.map((p) => (
          <button
            key={p} onClick={() => setPriority(priority === p ? '' : p)}
            className={`px-2.5 py-1 rounded-full border capitalize ${priority === p ? 'bg-slate-700 border-slate-500 text-white' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}
          >
            {p}{mix ? ` · ${mix[p]}` : ''}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 bg-slate-950/50">
                <th className="p-3">Case</th><th>Txn</th><th>Amount</th><th>Priority</th><th>Decision</th><th>Age</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr
                  key={c.id} onClick={() => setSelected(c)}
                  className={`border-t border-slate-800 cursor-pointer hover:bg-slate-800/40 ${selected?.id === c.id ? 'bg-slate-800/60' : ''}`}
                >
                  <td className="p-3 text-white">#{c.id}</td>
                  <td>{c.transaction_id != null ? `#${c.transaction_id}` : '—'}</td>
                  <td className="whitespace-nowrap">{money(c.amount, c.currency)}</td>
                  <td><RiskBadge level={String(c.priority || '').toUpperCase()} /></td>
                  <td>{decisionLabel(c.decision)}</td>
                  <td className="text-slate-500">{age(c.created_at)}</td>
                </tr>
              ))}
              {cases.length === 0 && (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-slate-500">
                    {queue === 'needs_review' ? 'Nothing waiting for review. New escalations appear here automatically.' : 'No cases in this queue.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {hasMore && (
            <div className="p-3 text-center border-t border-slate-800">
              <button
                onClick={loadMore} disabled={loadingMore}
                className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4">
          {!selected ? (
            <p className="text-slate-500 text-sm">Select a case to investigate.</p>
          ) : (
            <>
              <div>
                <h2 className="text-white font-semibold">Case #{selected.id}</h2>
                <p className="text-xs text-slate-500">
                  Alert #{selected.alert_id}
                  {selected.transaction_id != null && <> · Txn #{selected.transaction_id}</>}
                  {selected.amount != null && <> · {money(selected.amount, selected.currency)}</>}
                  {' · '}{decisionLabel(selected.decision)}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <select value={selected.status} onChange={(e) => update(selected.id, { status: e.target.value })} className="bg-slate-800 border border-slate-700 rounded p-2 text-sm">
                  <option>open</option><option>investigating</option><option>pending</option><option>closed</option>
                </select>
                <select value={selected.priority} onChange={(e) => update(selected.id, { priority: e.target.value })} className="bg-slate-800 border border-slate-700 rounded p-2 text-sm">
                  <option>low</option><option>medium</option><option>high</option><option>critical</option>
                </select>
              </div>
              <div className="flex gap-2">
                <button onClick={() => update(selected.id, { decision: 'confirmed_fraud', status: 'closed' })} className="px-3 py-2 rounded bg-red-700 text-white text-xs">Confirmed Fraud</button>
                <button onClick={() => update(selected.id, { decision: 'false_positive', status: 'closed' })} className="px-3 py-2 rounded bg-slate-700 text-white text-xs">False Positive</button>
              </div>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Investigation note..." className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-2 text-sm" />
              <button onClick={addNote} className="px-3 py-2 rounded bg-indigo-600 text-white text-sm">Add Note</button>
              <div className="space-y-2 max-h-48 overflow-auto">
                {selected.notes?.map((n) => (
                  <div key={n.id} className="border-l-2 border-indigo-500 pl-2">
                    <p className="text-sm text-slate-300 whitespace-pre-line">{n.note}</p>
                    <p className="text-xs text-slate-600">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
