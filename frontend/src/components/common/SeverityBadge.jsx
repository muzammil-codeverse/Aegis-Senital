import { normalizeSeverity, severityClass } from '../../utils/severity'

export default function SeverityBadge({ severity = 'info', compact = false }) {
  return (
    <span className={`severity-badge ${severityClass(severity)} ${compact ? 'is-compact' : ''}`}>
      {normalizeSeverity(severity)}
    </span>
  )
}
