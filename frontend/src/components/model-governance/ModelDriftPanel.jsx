import React, { useState } from 'react'

export default function ModelDriftPanel({ loadDrift }) {
  const [modelId, setModelId] = useState('weapon_yolo11s_v2_current')
  const [drift, setDrift] = useState(null)
  const [err, setErr] = useState(null)

  async function go() {
    setErr(null)
    try {
      const d = await loadDrift(modelId)
      setDrift(d)
    } catch (e) {
      setErr(e.message || String(e))
    }
  }

  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Drift</p>
          <h2>Telemetry-backed view</h2>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <input
          className="text-input"
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
          placeholder="model_id"
        />
        <button type="button" className="primary-button" onClick={go}>Load drift</button>
      </div>
      {err && <p className="muted" style={{ color: '#f85149' }}>{err}</p>}
      {drift && (
        <pre style={{ fontSize: 11, background: '#0d1117', padding: 12, borderRadius: 6, overflow: 'auto' }}>
          {JSON.stringify(drift, null, 2)}
        </pre>
      )}
    </section>
  )
}
