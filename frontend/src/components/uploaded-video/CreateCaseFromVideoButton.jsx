import { useState } from 'react'

export default function CreateCaseFromVideoButton({ session, disabled = false, onCreate }) {
  const [title, setTitle] = useState('')
  const [attachReplayClips, setAttachReplayClips] = useState(true)

  if (!session) return null

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Case Integration</p>
          <h2>Create Case</h2>
        </div>
        <span className="count-pill">{session.linked_case_id || 'new case'}</span>
      </div>
      <p className="muted">
        Promote the uploaded-video session into a case with hashed source evidence, snapshots, the generated report, and
        optional event-window replay clips when available.
      </p>
      <label className="button-row" style={{ alignItems: 'center', gap: '0.5rem' }}>
        <input
          type="checkbox"
          checked={attachReplayClips}
          onChange={event => setAttachReplayClips(event.target.checked)}
        />
        <span>Attach replay clips to case (hashed clip evidence when generated)</span>
      </label>
      <div className="button-row">
        <input
          aria-label="Case title override"
          value={title}
          onChange={event => setTitle(event.target.value)}
          placeholder="Optional case title override"
        />
        <button
          type="button"
          className="primary-button"
          disabled={disabled}
          onClick={() => onCreate(session.session_id, { title: title || undefined, attach_replay_clips: attachReplayClips })}
        >
          Create Case From Session
        </button>
      </div>
    </section>
  )
}
