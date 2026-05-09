import SeverityBadge from '../common/SeverityBadge'

export default function IncidentSeverityBadge({ severity }) {
  return <SeverityBadge severity={severity || 'info'} compact />
}
