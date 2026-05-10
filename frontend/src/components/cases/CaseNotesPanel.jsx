import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'

export default function CaseNotesPanel({ items = [], onAddNote, busy }) {
  const [note, setNote] = useState('')

  function submit(event) {
    event.preventDefault()
    if (!note.trim()) return
    onAddNote?.({ note })
    setNote('')
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Notes</h3>
        <span>{items.length} note(s)</span>
      </div>
      {items.length === 0 ? (
        <EmptyState message="No operator notes yet." />
      ) : (
        <div className="stack-list">
          {items.map(item => (
            <article key={item.note_id} className="case-subcard">
              <div className="alert-card-header">
                <strong>{item.created_by || 'operator'}</strong>
                <span>{formatTimestamp(item.created_at)}</span>
              </div>
              <p className="drawer-description">{item.note}</p>
            </article>
          ))}
        </div>
      )}
      <form className="case-inline-form" onSubmit={submit}>
        <input value={note} onChange={event => setNote(event.target.value)} placeholder="Add operator note" />
        <button type="submit" className="text-button" disabled={busy}>Add Note</button>
      </form>
    </section>
  )
}
