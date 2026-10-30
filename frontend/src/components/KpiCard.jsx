export default function KpiCard({ label, value, accent = 'text-slate-100', hint }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <span className={`text-2xl font-bold ${accent}`}>{value}</span>
      {hint && <span className="text-xs text-slate-500">{hint}</span>}
    </div>
  )
}
