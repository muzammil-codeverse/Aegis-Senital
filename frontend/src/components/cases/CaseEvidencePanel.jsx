import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'

export default function CaseEvidencePanel({ items = [], onAddEvidence, busy }) {
  const [form, setForm] = useState({
    evidence_type: 'external_link',
    title: '',
    description: '',
    source_event_id: '',
    storage_uri: '',
  })

  function submit(event) {
    event.preventDefault()
    onAddEvidence?.(form)
    setForm({ evidence_type: 'external_link', title: '', description: '', source_event_id: '', storage_uri: '' })
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Evidence</h3>
        <span>{items.length} item(s)</span>
      </div>
      {items.length === 0 ? (
        <EmptyState message="No evidence items attached." />
      ) : (
        <div className="stack-list">
          {items.map(item => (
            <article key={item.evidence_id} className="case-subcard">
              <div className="alert-card-header">
                <strong>{item.title || item.evidence_type}</strong>
                <span className="state-chip">{item.evidence_type}</span>
                <span className="state-chip">{item.integrity_status || 'not_applicable'}</span>
              </div>
              <p className="drawer-description">{item.description || 'Evidence item requires operator review.'}</p>
              <div className="drawer-grid">
                <span>Timestamp</span><strong>{formatTimestamp(item.timestamp || item.created_at)}</strong>
                <span>Camera</span><strong>{item.camera_id || 'N/A'}</strong>
                <span>Source Event</span><strong>{item.source_event_id || 'N/A'}</strong>
                <span>Hash</span><strong>{item.hash_sha256 || 'Metadata only'}</strong>
              </div>
            </article>
          ))}
        </div>
      )}
      <form className="case-inline-form" onSubmit={submit}>
        <select value={form.evidence_type} onChange={event => setForm(current => ({ ...current, evidence_type: event.target.value }))}>
          <option value="external_link">External Link</option>
          <option value="event">Event</option>
          <option value="attachment">Attachment</option>
          <option value="system_report">System Report</option>
        </select>
        <input value={form.title} onChange={event => setForm(current => ({ ...current, title: event.target.value }))} placeholder="Evidence title" />
        <input value={form.source_event_id} onChange={event => setForm(current => ({ ...current, source_event_id: event.target.value }))} placeholder="Source event ID" />
        <input value={form.storage_uri} onChange={event => setForm(current => ({ ...current, storage_uri: event.target.value }))} placeholder="Reference URI" />
        <button type="submit" className="text-button" disabled={busy}>Attach</button>
      </form>
    </section>
  )
}
