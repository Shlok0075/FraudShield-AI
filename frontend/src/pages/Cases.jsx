import { useEffect, useRef, useState } from 'react'
import api from '../services/api'

const PAGE_SIZE = 100

export default function Cases() {
  const [cases,setCases]=useState([]); const [selected,setSelected]=useState(null); const [note,setNote]=useState('')
  const [hasMore,setHasMore]=useState(false); const [loadingMore,setLoadingMore]=useState(false)
  const loadedCount=useRef(0)
  // Fetch in pages (server default 100, max 500) and keep reloads to what is already on screen.
  async function load(){
    const limit=Math.min(500,Math.max(PAGE_SIZE,loadedCount.current))
    const {data}=await api.get('/cases',{params:{limit,offset:0}})
    loadedCount.current=data.length; setCases(data); setHasMore(data.length===limit)
  }
  async function loadMore(){
    setLoadingMore(true)
    try{
      const {data}=await api.get('/cases',{params:{limit:PAGE_SIZE,offset:loadedCount.current}})
      loadedCount.current+=data.length; setCases(prev=>[...prev,...data]); setHasMore(data.length===PAGE_SIZE)
    } finally { setLoadingMore(false) }
  }
  useEffect(()=>{load()},[])
  async function update(id, body){ await api.patch(`/cases/${id}`,body); await load(); if(selected?.id===id){const {data}=await api.get(`/cases/${id}`);setSelected(data)} }
  async function addNote(){ if(!note.trim()) return; await api.post(`/cases/${selected.id}/notes`,{note}); setNote(''); const {data}=await api.get(`/cases/${selected.id}`); setSelected(data); load() }
  return <div className="p-6 max-w-7xl mx-auto space-y-5">
    <div><h1 className="text-xl font-bold text-white">Investigation Cases</h1><p className="text-sm text-slate-500">Human-in-the-loop fraud investigation and feedback.</p></div>
    <div className="grid lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <table className="w-full text-sm"><thead><tr className="text-left text-slate-500 bg-slate-950/50"><th className="p-3">Case</th><th>Alert</th><th>Priority</th><th>Status</th><th>Decision</th></tr></thead><tbody>
        {cases.map(c=><tr key={c.id} onClick={()=>setSelected(c)} className="border-t border-slate-800 cursor-pointer hover:bg-slate-800/40"><td className="p-3 text-white">#{c.id}</td><td>#{c.alert_id}</td><td className="capitalize">{c.priority}</td><td className="capitalize">{c.status}</td><td>{c.decision||'—'}</td></tr>)}
        {cases.length===0&&<tr><td colSpan="5" className="p-8 text-center text-slate-500">No cases yet. New REVIEW/BLOCK alerts create cases automatically.</td></tr>}
        </tbody></table>
        {hasMore&&<div className="p-3 text-center border-t border-slate-800"><button onClick={loadMore} disabled={loadingMore} className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-sm text-white hover:bg-slate-700 disabled:opacity-50">{loadingMore?'Loading…':'Load more'}</button></div>}
      </div>
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4">
        {!selected?<p className="text-slate-500 text-sm">Select a case to investigate.</p>:<>
          <div><h2 className="text-white font-semibold">Case #{selected.id}</h2><p className="text-xs text-slate-500">Alert #{selected.alert_id}</p></div>
          <div className="grid grid-cols-2 gap-2">
            <select value={selected.status} onChange={e=>update(selected.id,{status:e.target.value})} className="bg-slate-800 border border-slate-700 rounded p-2 text-sm"><option>open</option><option>investigating</option><option>pending</option><option>closed</option></select>
            <select value={selected.priority} onChange={e=>update(selected.id,{priority:e.target.value})} className="bg-slate-800 border border-slate-700 rounded p-2 text-sm"><option>low</option><option>medium</option><option>high</option><option>critical</option></select>
          </div>
          <div className="flex gap-2"><button onClick={()=>update(selected.id,{decision:'confirmed_fraud',status:'closed'})} className="px-3 py-2 rounded bg-red-700 text-white text-xs">Confirmed Fraud</button><button onClick={()=>update(selected.id,{decision:'false_positive',status:'closed'})} className="px-3 py-2 rounded bg-slate-700 text-white text-xs">False Positive</button></div>
          <textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="Investigation note..." className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-2 text-sm" />
          <button onClick={addNote} className="px-3 py-2 rounded bg-indigo-600 text-white text-sm">Add Note</button>
          <div className="space-y-2 max-h-48 overflow-auto">{selected.notes?.map(n=><div key={n.id} className="border-l-2 border-indigo-500 pl-2"><p className="text-sm text-slate-300">{n.note}</p><p className="text-xs text-slate-600">{new Date(n.created_at).toLocaleString()}</p></div>)}</div>
        </>}
      </div>
    </div>
  </div>
}
