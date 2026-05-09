import { useState } from 'react'

const SEVERITY_COLORS = {
  low: '#34d399', medium: '#fbbf24', high: '#f97316', critical: '#ef4444',
}

const CATEGORIES = [
  'suspicious_object', 'suspicious_behavior', 'identity_obscuration',
  'forced_entry_tool', 'weapon', 'crowd_anomaly', 'other',
]

/**
 * PromptLibraryPanel — table of open-vocab prompts with enable/disable/edit.
 * Includes an inline form for adding new prompts.
 */
export default function PromptLibraryPanel({ prompts, onDisable, onUpdate, onCreate, loading }) {
  const [showForm, setShowForm] = useState(false)
  const [formState, setFormState] = useState({ text: '', category: 'suspicious_object', severity: 'medium', threshold: '' })
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [editId, setEditId] = useState(null)
  const [editState, setEditState] = useState({})

  async function handleCreate(e) {
    e.preventDefault()
    setFormError(null)
    if (!formState.text.trim()) { setFormError('Prompt text is required.'); return }
    setSubmitting(true)
    try {
      await onCreate({
        text: formState.text.trim(),
        category: formState.category,
        severity: formState.severity,
        threshold: formState.threshold ? parseFloat(formState.threshold) : undefined,
      })
      setFormState({ text: '', category: 'suspicious_object', severity: 'medium', threshold: '' })
      setShowForm(false)
    } catch (err) {
      setFormError(err?.message || 'Failed to create prompt')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleUpdate(promptId) {
    try {
      await onUpdate(promptId, editState)
      setEditId(null)
      setEditState({})
    } catch (err) {
      // silently fail — parent error state handles it
    }
  }

  function startEdit(prompt) {
    setEditId(prompt.prompt_id)
    setEditState({ severity: prompt.severity, threshold: String(prompt.threshold ?? '') })
  }

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Threat Prompts</p>
          <h2>Prompt Library</h2>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="count-pill">{prompts.length}</span>
          <button className="ctrl-btn" onClick={() => setShowForm(v => !v)}>
            {showForm ? '− Cancel' : '+ Add Prompt'}
          </button>
        </div>
      </div>

      {/* Add prompt form */}
      {showForm && (
        <form onSubmit={handleCreate} style={{ padding: '10px 12px', borderBottom: '1px solid #1c2535', display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
          <div style={{ flex: '2 1 200px' }}>
            <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Prompt Text *</label>
            <input
              type="text"
              value={formState.text}
              onChange={e => setFormState(s => ({ ...s, text: e.target.value }))}
              placeholder="e.g. unattended bag or backpack"
              style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '4px 8px', fontSize: '0.78rem' }}
            />
          </div>
          <div style={{ flex: '1 1 120px' }}>
            <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Category</label>
            <select
              value={formState.category}
              onChange={e => setFormState(s => ({ ...s, category: e.target.value }))}
              style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '4px 6px', fontSize: '0.75rem' }}
            >
              {CATEGORIES.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          <div style={{ flex: '1 1 90px' }}>
            <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Severity</label>
            <select
              value={formState.severity}
              onChange={e => setFormState(s => ({ ...s, severity: e.target.value }))}
              style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '4px 6px', fontSize: '0.75rem' }}
            >
              {['low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div style={{ flex: '0 1 80px' }}>
            <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Threshold</label>
            <input
              type="number"
              step="0.01" min="0" max="1"
              value={formState.threshold}
              onChange={e => setFormState(s => ({ ...s, threshold: e.target.value }))}
              placeholder="0.35"
              style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '4px 6px', fontSize: '0.75rem' }}
            />
          </div>
          <button type="submit" className="ctrl-btn ctrl-btn-start" disabled={submitting}>
            {submitting ? 'Adding…' : 'Add'}
          </button>
          {formError && <span style={{ width: '100%', color: '#f87171', fontSize: '0.7rem' }}>{formError}</span>}
        </form>
      )}

      {/* Prompts table */}
      <div style={{ overflowX: 'auto' }}>
        {loading && prompts.length === 0 && (
          <p style={{ color: '#6b7280', fontSize: '0.78rem', padding: '10px 12px' }}>Loading prompts…</p>
        )}
        {!loading && prompts.length === 0 && (
          <p style={{ color: '#6b7280', fontSize: '0.78rem', padding: '10px 12px' }}>No prompts in library.</p>
        )}
        {prompts.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1c2535', color: '#4b5563', textTransform: 'uppercase', fontSize: '0.6rem', letterSpacing: 1 }}>
                <th style={{ padding: '6px 12px', textAlign: 'left' }}>Text</th>
                <th style={{ padding: '6px 8px', textAlign: 'left' }}>Category</th>
                <th style={{ padding: '6px 8px', textAlign: 'left' }}>Severity</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Threshold</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Status</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {prompts.map(p => {
                const isEditing = editId === p.prompt_id
                return (
                  <tr
                    key={p.prompt_id}
                    style={{ borderBottom: '1px solid #111827', opacity: p.enabled ? 1 : 0.5 }}
                  >
                    <td style={{ padding: '6px 12px', color: '#e5e7eb' }}>
                      {p.text}
                    </td>
                    <td style={{ padding: '6px 8px', color: '#9ca3af' }}>
                      {(p.category || '').replace(/_/g, ' ')}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      {isEditing ? (
                        <select
                          value={editState.severity ?? p.severity}
                          onChange={e => setEditState(s => ({ ...s, severity: e.target.value }))}
                          style={{ background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '2px 4px', fontSize: '0.72rem' }}
                        >
                          {['low', 'medium', 'high', 'critical'].map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                      ) : (
                        <span style={{ color: SEVERITY_COLORS[p.severity] || '#9ca3af', fontWeight: 600 }}>
                          {p.severity}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center', color: '#6b7280' }}>
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.01" min="0" max="1"
                          value={editState.threshold ?? String(p.threshold)}
                          onChange={e => setEditState(s => ({ ...s, threshold: parseFloat(e.target.value) }))}
                          style={{ width: 60, background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '2px 4px', fontSize: '0.72rem' }}
                        />
                      ) : (
                        p.threshold?.toFixed(2)
                      )}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      <span style={{
                        padding: '1px 6px', borderRadius: 10, fontSize: '0.6rem', fontWeight: 700,
                        background: p.enabled ? '#052e16' : '#1f2937',
                        color: p.enabled ? '#34d399' : '#6b7280',
                      }}>
                        {p.enabled ? 'ON' : 'OFF'}
                      </span>
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      {isEditing ? (
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                          <button className="ctrl-btn ctrl-btn-start" onClick={() => handleUpdate(p.prompt_id)} style={{ fontSize: '0.65rem' }}>Save</button>
                          <button className="ctrl-btn" onClick={() => { setEditId(null); setEditState({}) }} style={{ fontSize: '0.65rem' }}>Cancel</button>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                          <button className="ctrl-btn" onClick={() => startEdit(p)} style={{ fontSize: '0.65rem' }}>Edit</button>
                          {p.enabled && (
                            <button className="ctrl-btn ctrl-btn-stop" onClick={() => onDisable(p.prompt_id)} style={{ fontSize: '0.65rem' }}>Disable</button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
