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
  auto_cleared: 'Auto-cleared', auto_clear: 'Auto-cleared',
  auto_blocked: 'Auto-blocked', auto_block: 'Auto-blocked',
  needs_review: 'Needs review', review: 'Needs review', unresolved: 'Needs review',
  confirmed_fraud: 'Confirmed fraud', false_positive: 'False positive',
}
const decisionLabel = (d) => DECISION_LABEL[String(d || '').toLowerCase()] || (d ? String(d) : 'Needs review')

// What the analyst can do in one click, per queue. The system's verdict is already on the case;
// these only record a human decision (the server closes and assigns the case automatically).
const ACTIONS = {
  needs_review: [
    { label: 'Confirm fraud', decision: 'confirmed_fraud', tone: 'bg-red-700 hover:bg-red-600' },
    { label: 'Mark legitimate', decision: 'false_positive', tone: 'bg-emerald-700 hover:bg-emerald-600' },
  ],
  auto_blocked: [
    { label: 'Confirm fraud (keep blocked)', decision: 'confirmed_fraud', tone: 'bg-red-700 hover:bg-red-600' },
    { label: 'Overturn: legitimate', decision: 'false_positive', tone: 'bg-slate-700 hover:bg-slate-600' },
  ],
  auto_cleared: [
    { label: 'Agree: legitimate', decision: 'false_positive', tone: 'bg-emerald-700 hover:bg-emerald-600' },
    { label: 'Wrong: this is fraud', decision: 'confirmed_fraud', tone: 'bg-red-700 hover:bg-red-600' },
  ],
  closed: [],
}

function Bar({ value, tone = 'bg-indigo-500' }) {
  return (
    <div className="h-1.5 rounded bg-slate-800 overflow-hidden">
      <div className={`h-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

function age(ts) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(ts + (String(ts).endsWith('Z') ? '' : 'Z')).getTime()) / 60000))
  if (mins < 60) return `${mins}m`
  if (mins < 60 * 48) return `${Math.round(mins / 60)}h`
  return `${Math.round(mins / 1440)}d`
}

const money = (amount, currency) =>
  amount == null ? '—' : `${currency || ''} ${Number(amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}`.trim()

function CasePanel({ c, note, setNote, addNote, onDecide }) {
  const inv = c.investigation
  const actions = ACTIONS[c.queue] || []
  const riskTone = { CRITICAL: 'text-red-400', HIGH: 'text-orange-400', MEDIUM: 'text-yellow-400', LOW: 'text-emerald-400' }[inv?.risk_level] || 'text-slate-300'
  return (
    <>
      <div>
        <h2 className="text-white font-semibold">Case #{c.id} <span className="ml-1 text-xs font-normal text-slate-400">{decisionLabel(c.decision)}</span></h2>
        <p className="text-xs text-slate-500">
          Alert #{c.alert_id}
          {c.transaction_id != null && <> · Txn #{c.transaction_id}</>}
          {c.amount != null && <> · {money(c.amount, c.currency)}</>}
        </p>
      </div>

      {inv ? (
        <>
          <div className="rounded-lg bg-slate-950 border border-slate-800 p-3 space-y-2">
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-slate-500">Automated confidence</span>
              <span className={`text-sm font-semibold ${riskTone}`}>{inv.confidence}% · {inv.risk_level}</span>
            </div>
            <Bar value={inv.confidence} tone={inv.confidence >= 80 ? 'bg-red-500' : inv.confidence >= 50 ? 'bg-yellow-500' : 'bg-emerald-500'} />
            {inv.reasoning && <p className="text-xs text-slate-400">{inv.reasoning}</p>}
          </div>

          {inv.signals.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wide text-slate-500">Evidence</p>
              {inv.signals.map((s) => (
                <div key={s.name}>
                  <div className="flex justify-between text-xs text-slate-300"><span>{s.name}</span><span>{s.score}%</span></div>
                  <Bar value={s.score} />
                </div>
              ))}
            </div>
          )}

          {inv.checks.length > 0 && (
            <ul className="text-xs text-slate-300 space-y-1 list-disc pl-4">
              {inv.checks.map((t) => <li key={t}>{t}</li>)}
            </ul>
          )}

          {inv.recommendation && (
            <p className="text-xs rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-200 p-2">
              <span className="font-semibold">Recommended: </span>{inv.recommendation}
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-slate-500">No automated report on this case yet. The investigator will pick it up on its next sweep.</p>
      )}

      {actions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {actions.map((a) => (
            <button key={a.decision} onClick={() => onDecide(a.decision)} className={`px-3 py-2 rounded text-white text-xs ${a.tone}`}>{a.label}</button>
          ))}
        </div>
      ) : (
        <p className="text-xs text-slate-500">Closed. Status and assignee were set automatically.</p>
      )}

      <details className="text-sm">
        <summary className="cursor-pointer text-xs text-slate-500">Notes{c.notes?.length ? ` (${c.notes.length})` : ''} · optional</summary>
        <div className="mt-2 space-y-2">
          <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add context for the next analyst..." className="w-full h-20 bg-slate-950 border border-slate-700 rounded p-2 text-sm" />
          <button onClick={addNote} className="px-3 py-1.5 rounded bg-indigo-600 text-white text-xs">Add note</button>
          {c.notes?.map((n) => (
            <div key={n.id} className="border-l-2 border-indigo-500 pl-2">
              <p className="text-sm text-slate-300 whitespace-pre-line">{n.note}</p>
              <p className="text-xs text-slate-600">{new Date(n.created_at).toLocaleString()}</p>
            </div>
          ))}
        </div>
      </details>
    </>
  )
}

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

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4 self-start">
          {!selected ? (
            <p className="text-slate-500 text-sm">Select a case. The automated investigation is shown here.</p>
          ) : (
            <CasePanel
              c={selected} note={note} setNote={setNote} addNote={addNote}
              onDecide={(decision) => update(selected.id, { decision })}
            />
          )}
        </div>
      </div>
    </div>
  )
}
