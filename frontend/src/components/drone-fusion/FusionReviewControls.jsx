import { useState } from 'react'

export default function FusionReviewControls({ correlationId, reviewStatus, onReview }) {
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)

  if (reviewStatus !== 'pending') {
    return <span style={{ color: '#6b7280', fontSize: 12 }}>Review: {reviewStatus}</span>
  }

  const handle = async (action) => {
    setBusy(true)
    try { await onReview(correlationId, action, notes) } finally { setBusy(false) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <input
        aria-label="Review notes"
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="Review notes (optional)"
        style={{ fontSize: 12, padding: '2px 6px', background: '#1f2937', border: '1px solid #374151', color: '#f9fafb', borderRadius: 4 }}
      />
      <div style={{ display: 'flex', gap: 4 }}>
        <button disabled={busy} onClick={() => handle('accept')}
          style={{ background: '#065f46', color: '#fff', border: 'none', padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
          Accept
        </button>
        <button disabled={busy} onClick={() => handle('reject')}
          style={{ background: '#7f1d1d', color: '#fff', border: 'none', padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
          Reject
        </button>
        <button disabled={busy} onClick={() => handle('inconclusive')}
          style={{ background: '#374151', color: '#fff', border: 'none', padding: '3px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
          Inconclusive
        </button>
      </div>
    </div>
  )
}
