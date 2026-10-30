const LEVEL_CLASSES = {
  LOW: 'risk-low bg-risk-low',
  MEDIUM: 'risk-medium bg-risk-medium',
  HIGH: 'risk-high bg-risk-high',
  CRITICAL: 'risk-critical bg-risk-critical',
}

export default function RiskBadge({ level }) {
  const cls = LEVEL_CLASSES[level] || 'text-slate-400 bg-slate-800'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {level}
    </span>
  )
}
