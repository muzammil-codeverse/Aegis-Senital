import CasePriorityBadge from './CasePriorityBadge'
import CaseStatusBadge from './CaseStatusBadge'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatTimestamp } from '../../utils/time'

export default function CaseList({
  cases = [],
  selectedCaseId,
  loading,
  error,
  onSelect,
  onRetry,
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Case Queue</p>
          <h2>Cases</h2>
        </div>
        <span className="count-pill">{cases.length}</span>
      </div>
      {loading && <LoadingState label="Loading cases" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && cases.length === 0 && (
        <EmptyState message="No cases created yet. Cases are generated automatically from high-severity incidents or can be created manually from an uploaded video analysis or incident event." />
      )}
      <div className="stack-list">
        {cases.map(item => (
          <article
            key={item.case_id}
            className={`incident-card ${selectedCaseId === item.case_id ? 'selected' : ''}`}
            onClick={() => onSelect?.(item.case_id)}
          >
            <div className="incident-card-top">
              <CaseStatusBadge status={item.status} />
              <CasePriorityBadge priority={item.priority} />
              <span className="alert-age">{formatTimestamp(item.updated_at || item.created_at)}</span>
            </div>
            <h3>{item.title || item.case_id}</h3>
            <p>{item.description || 'Possible incident awaiting operator review.'}</p>
            <div className="incident-grid">
              <span>Case ID</span><strong>{item.case_id}</strong>
              <span>Camera</span><strong>{(item.camera_ids || []).join(', ') || 'N/A'}</strong>
              <span>Assigned</span><strong>{item.assigned_to || 'Unassigned'}</strong>
              <span>Events</span><strong>{(item.source_event_ids || []).length}</strong>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
