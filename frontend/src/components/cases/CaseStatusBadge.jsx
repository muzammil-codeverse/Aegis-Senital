export default function CaseStatusBadge({ status = 'open' }) {
  const label = String(status || 'open').replace('_', ' ')
  return <span className={`case-status-badge case-status-${label}`}>{label}</span>
}
