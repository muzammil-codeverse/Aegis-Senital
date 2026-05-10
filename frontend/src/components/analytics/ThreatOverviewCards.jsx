import clsx from 'clsx'
import { Activity, AlertTriangle, Camera, Clock3, FolderOpen, Radar, ShieldAlert, Siren } from 'lucide-react'
import { formatNumber } from '../../utils/formatters'

const CARD_CONFIG = [
  { key: 'total_events', label: 'Total events', icon: Radar },
  { key: 'critical_events', label: 'Critical events', icon: Siren, tone: 'critical' },
  { key: 'open_cases', label: 'Open cases', icon: FolderOpen },
  { key: 'cases_requiring_review', label: 'Require review', icon: ShieldAlert, tone: 'warning' },
  { key: 'active_streams', label: 'Active streams', icon: Activity },
  { key: 'degraded_streams', label: 'Degraded streams', icon: AlertTriangle, tone: 'warning' },
  { key: 'avg_model_latency_ms', label: 'Avg inference latency', icon: Clock3, suffix: ' ms' },
]

export default function ThreatOverviewCards({ overview }) {
  const cards = CARD_CONFIG.map(card => ({
    ...card,
    value: overview?.summary?.[card.key] ?? 0,
  }))
  cards.push({
    key: 'highest_risk_camera',
    label: 'Highest-risk camera',
    icon: Camera,
    tone: 'critical',
    value: overview?.risk?.highest_risk_camera || 'No active camera risk',
    meta: overview?.risk?.highest_risk_score ? `${overview.risk.highest_risk_score.toFixed(1)} score` : '0.0 score',
  })

  return (
    <div className="analytics-card-grid">
      {cards.map(card => {
        const Icon = card.icon
        const numeric = typeof card.value === 'number'
        return (
          <article key={card.key} className={clsx('analytics-overview-card', card.tone && `is-${card.tone}`)}>
            <div className="analytics-overview-card-top">
              <span>{card.label}</span>
              <Icon size={16} />
            </div>
            <strong>{numeric ? `${formatNumber(card.value)}${card.suffix || ''}` : card.value}</strong>
            <small>{card.meta || 'Computed from stored events, cases, and runtime metrics.'}</small>
          </article>
        )
      })}
    </div>
  )
}
