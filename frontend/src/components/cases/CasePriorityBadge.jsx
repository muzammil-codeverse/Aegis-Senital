import SeverityBadge from '../common/SeverityBadge'

export default function CasePriorityBadge({ priority = 'medium' }) {
  return <SeverityBadge severity={priority} compact />
}
