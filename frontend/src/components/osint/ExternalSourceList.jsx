import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'
import SourceReliabilityBadge from './SourceReliabilityBadge'

export default function ExternalSourceList({ items = [], busy, canWrite, onDelete, onUpdateReliability }) {
  const [draftReliability, setDraftReliability] = useState({})

  if (!items.length) {
    return <EmptyState message="No analyst-provided enrichment sources yet. Add external links, upload documents, or record analyst notes using the forms above. OSINT provider not configured — local demo enrichment continues without LLM summaries." />
  }

  return (
    <div className="stack-list">
      {items.map(item => {
        const currentReliability = draftReliability[item.source_id] || item.source_reliability || 'unknown'
        return (
          <article key={item.source_id} className="case-subcard">
            <div className="alert-card-header">
              <strong>{item.title || 'Manual source'}</strong>
              <span className="state-chip">{item.source_type}</span>
              <span className="state-chip">{item.requires_review ? 'Requires operator review' : 'reviewed'}</span>
            </div>
            <p className="drawer-description">{item.description || 'Analyst-provided enrichment source.'}</p>
            <div className="button-row">
              <SourceReliabilityBadge value={item.source_reliability} />
              {item.metadata?.domain ? <span className="state-chip">{item.metadata.domain}</span> : null}
              {item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="text-button">Open Link</a> : null}
            </div>
            <div className="drawer-grid">
              <span>Source ID</span><strong>{item.source_id}</strong>
              <span>Created</span><strong>{formatTimestamp(item.created_at)}</strong>
              <span>Created By</span><strong>{item.created_by || 'operator'}</strong>
              <span>Summary</span><strong>{item.summary ? 'available' : 'pending'}</strong>
            </div>
            {canWrite ? (
              <div className="button-row">
                <select value={currentReliability} onChange={event => setDraftReliability(current => ({ ...current, [item.source_id]: event.target.value }))}>
                  <option value="unknown">Reliability unknown</option>
                  <option value="low">Reliability low</option>
                  <option value="medium">Reliability medium</option>
                  <option value="high">Reliability high</option>
                </select>
                <button type="button" className="text-button" disabled={busy} onClick={() => onUpdateReliability?.(item.source_id, currentReliability)}>
                  Update
                </button>
                <button type="button" className="text-button danger" disabled={busy} onClick={() => onDelete?.(item.source_id)}>
                  Delete
                </button>
              </div>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
