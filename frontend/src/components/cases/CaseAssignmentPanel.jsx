import { useState } from 'react'

export default function CaseAssignmentPanel({ caseItem, onAssign, busy }) {
  const [assignedTo, setAssignedTo] = useState(caseItem?.assigned_to || '')
  const [reason, setReason] = useState('')

  function submit(event) {
    event.preventDefault()
    if (!assignedTo.trim()) return
    onAssign?.(assignedTo, reason)
    setReason('')
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Assignment</h3>
        <span>{caseItem?.assigned_to || 'Unassigned'}</span>
      </div>
      <form className="case-inline-form" onSubmit={submit}>
        <input value={assignedTo} onChange={event => setAssignedTo(event.target.value)} placeholder="Assignee username" />
        <input value={reason} onChange={event => setReason(event.target.value)} placeholder="Assignment note" />
        <button type="submit" className="text-button" disabled={busy}>Assign</button>
      </form>
    </section>
  )
}
