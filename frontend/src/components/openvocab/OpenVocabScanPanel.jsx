import { useState, useRef } from 'react'

/**
 * OpenVocabScanPanel — allows operator to trigger open-vocabulary scans:
 * - Scan latest frame from a camera
 * - Upload and scan an image
 * - Scan by incident ID
 */
export default function OpenVocabScanPanel({ onScanCamera, onScanImage, onScanIncident, loading, cameras }) {
  const [mode, setMode] = useState('camera') // 'camera' | 'image' | 'incident'
  const [cameraId, setCameraId] = useState('')
  const [incidentId, setIncidentId] = useState('')
  const [promptText, setPromptText] = useState('')
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState(null)
  const [lastResult, setLastResult] = useState(null)
  const fileRef = useRef(null)

  function parsePrompts() {
    return promptText.trim()
      ? promptText.split('\n').map(l => l.trim()).filter(Boolean)
      : undefined
  }

  async function handleScanCamera(e) {
    e.preventDefault()
    if (!cameraId.trim()) return
    setScanning(true)
    setError(null)
    setLastResult(null)
    try {
      const res = await onScanCamera(cameraId.trim(), parsePrompts())
      setLastResult(res)
    } catch (err) {
      setError(err?.message || 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  async function handleScanImage(e) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) { setError('Please select an image file.'); return }
    setScanning(true)
    setError(null)
    setLastResult(null)
    try {
      const res = await onScanImage(file, parsePrompts())
      setLastResult(res)
    } catch (err) {
      setError(err?.message || 'Image scan failed')
    } finally {
      setScanning(false)
    }
  }

  async function handleScanIncident(e) {
    e.preventDefault()
    if (!incidentId.trim()) return
    setScanning(true)
    setError(null)
    setLastResult(null)
    try {
      const res = await onScanIncident(incidentId.trim(), parsePrompts())
      setLastResult(res)
    } catch (err) {
      setError(err?.message || 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const resultStatus = lastResult?.item?.status || lastResult?.status

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Threat Analysis</p>
          <h2>Open-Vocab Scan</h2>
        </div>
      </div>

      <div style={{ padding: '10px 12px' }}>
        {/* Mode selector */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          {[['camera', 'Camera Frame'], ['image', 'Upload Image'], ['incident', 'Incident']].map(([m, label]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding: '4px 12px', borderRadius: 4, fontSize: '0.72rem', fontWeight: 600,
                cursor: 'pointer', border: '1px solid',
                borderColor: mode === m ? '#3b82f6' : '#374151',
                background: mode === m ? '#1e3a5f' : '#111827',
                color: mode === m ? '#93c5fd' : '#9ca3af',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Prompt override textarea */}
        <div style={{ marginBottom: 10 }}>
          <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3, textTransform: 'uppercase', letterSpacing: 1 }}>
            Prompt Overrides (one per line, leave empty to use library)
          </label>
          <textarea
            rows={3}
            value={promptText}
            onChange={e => setPromptText(e.target.value)}
            placeholder="e.g. unattended bag or backpack&#10;person wearing a mask"
            style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '6px 8px', fontSize: '0.75rem', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </div>

        {/* Camera scan */}
        {mode === 'camera' && (
          <form onSubmit={handleScanCamera} style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Camera ID</label>
              {cameras?.length > 0 ? (
                <select
                  value={cameraId}
                  onChange={e => setCameraId(e.target.value)}
                  style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '5px 8px', fontSize: '0.78rem' }}
                >
                  <option value="">Select camera…</option>
                  {cameras.map(c => (
                    <option key={c.camera_id} value={c.camera_id}>{c.name || c.camera_id}</option>
                  ))}
                </select>
              ) : (
                <input
                  aria-label="Camera ID"
                  type="text"
                  value={cameraId}
                  onChange={e => setCameraId(e.target.value)}
                  placeholder="e.g. cam-001"
                  style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '5px 8px', fontSize: '0.78rem' }}
                />
              )}
            </div>
            <button type="submit" className="ctrl-btn ctrl-btn-start" disabled={scanning || !cameraId.trim()}>
              {scanning ? 'Scanning…' : 'Scan Frame'}
            </button>
          </form>
        )}

        {/* Image upload scan */}
        {mode === 'image' && (
          <form onSubmit={handleScanImage} style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Image File (.jpg .jpeg .png, max 10 MB)</label>
              <input
                ref={fileRef}
                aria-label="Upload image for scan"
                type="file"
                accept=".jpg,.jpeg,.png"
                style={{ color: '#e5e7eb', fontSize: '0.75rem' }}
              />
            </div>
            <button type="submit" className="ctrl-btn ctrl-btn-start" disabled={scanning}>
              {scanning ? 'Scanning…' : 'Scan Image'}
            </button>
          </form>
        )}

        {/* Incident scan */}
        {mode === 'incident' && (
          <form onSubmit={handleScanIncident} style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '0.6rem', color: '#4b5563', marginBottom: 3 }}>Incident ID</label>
              <input
                aria-label="Incident ID"
                type="text"
                value={incidentId}
                onChange={e => setIncidentId(e.target.value)}
                placeholder="incident-uuid"
                style={{ width: '100%', background: '#0a0f1a', border: '1px solid #374151', color: '#e5e7eb', borderRadius: 3, padding: '5px 8px', fontSize: '0.78rem' }}
              />
            </div>
            <button type="submit" className="ctrl-btn ctrl-btn-start" disabled={scanning || !incidentId.trim()}>
              {scanning ? 'Scanning…' : 'Scan Incident'}
            </button>
          </form>
        )}

        {/* Error */}
        {error && (
          <div style={{ marginTop: 8, color: '#f87171', fontSize: '0.72rem' }}>{error}</div>
        )}

        {/* Scan result summary */}
        {lastResult && (
          <div style={{
            marginTop: 10, background: '#0a0f1a', border: '1px solid #1c2535',
            borderRadius: 4, padding: '8px 12px', fontSize: '0.75rem',
          }}>
            <p style={{ margin: '0 0 5px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1 }}>
              Last Scan Result
            </p>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <span style={{ color: '#6b7280' }}>
                Status: <strong style={{
                  color: resultStatus === 'completed' ? '#34d399' : resultStatus === 'unavailable' ? '#fbbf24' : '#f87171',
                }}>
                  {resultStatus || '—'}
                </strong>
              </span>
              {lastResult?.item?.risk_score != null && (
                <span style={{ color: '#6b7280' }}>
                  Risk: <strong style={{ color: '#e5e7eb' }}>{(lastResult.item.risk_score * 100).toFixed(1)}%</strong>
                </span>
              )}
              {lastResult?.item?.detections != null && (
                <span style={{ color: '#6b7280' }}>
                  Detections: <strong style={{ color: '#e5e7eb' }}>{lastResult.item.detections.length}</strong>
                </span>
              )}
              {lastResult?.item?.error && (
                <span style={{ color: '#fbbf24' }}>
                  {lastResult.item.error}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
