import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'

export default function CaseTimeline({ items = [] }) {
  if (!items.length) return <EmptyState message="No timeline items recorded yet." />
  return (
    <ol className="timeline-list">
      {items.map(item => (
        <li key={item.timeline_id || `${item.timestamp}-${item.sequence}`}>
          <span>{formatTimestamp(item.timestamp)}</span>
          <strong>{item.title || item.type || 'timeline item'}</strong>
          <em>{item.severity || item.type || 'event'}</em>
        </li>
      ))}
    </ol>
  )
}
