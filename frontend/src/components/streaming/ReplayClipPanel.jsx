import { useState } from 'react'
import { normalizeError } from '../../api/client'
import { exportReplayClip, getReplayClipUrl } from '../../api/streamingApi'
import { API_BASE_URL } from '../../config'

export default function ReplayClipPanel({ cameraId, caseId = null, defaultSeverity = 'high', onCreated }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [clip, setClip] = useState(null)

  async function handleExport() {
    if (!cameraId) return
    setBusy(true)
    setError(null)
    try {
      const response = await exportReplayClip(cameraId, {
        case_id: caseId || undefined,
        attach_to_case: Boolean(caseId),
        severity: defaultSeverity,
      })
      setClip(response.item)
      onCreated?.(response.item)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="panel-header" style={{ marginBottom: 10 }}>
        <div>
          <p className="eyebrow">Replay Export</p>
          <h2 style={{ fontSize: '0.95rem' }}>Evidence Clip</h2>
        </div>
      </div>
      <button type="button" className="text-button" disabled={busy || !cameraId} onClick={handleExport}>
        {busy ? 'Exporting…' : caseId ? 'Export And Attach' : 'Export Clip'}
      </button>
      {error && <div style={{ marginTop: 8, color: '#ff7875', fontSize: '0.72rem' }}>{error}</div>}
      {clip && (
        <div style={{ marginTop: 8, fontSize: '0.72rem', color: '#d1d5db' }}>
          <div>Status: {clip.status}</div>
          {clip.clip_id && (
            <a href={`${API_BASE_URL}${getReplayClipUrl(cameraId, clip.clip_id)}`} target="_blank" rel="noreferrer">
              Open replay clip
            </a>
          )}
        </div>
      )}
    </section>
  )
}
