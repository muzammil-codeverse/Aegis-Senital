import React, { useState } from 'react'
import { useAuth } from '../../hooks/useAuth'
import { postGovernanceRollback } from '../../api/modelGovernanceApi.js'

export default function ModelRollbackPanel() {
  const auth = useAuth()
  const canRollback = auth.hasPermission('model:rollback')
  const [modelKey, setModelKey] = useState('weapon_detector')
  const [version, setVersion] = useState('v1')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState(null)

  async function submit() {
    setMsg(null)
    try {
      const res = await postGovernanceRollback({ model_key: modelKey, target_version: version, reason })
      setMsg(JSON.stringify(res))
    } catch (e) {
      setMsg(e.response?.data?.detail || e.message || String(e))
    }
  }

  if (!canRollback) {
    return (
      <section className="panel" style={{ marginBottom: 16 }}>
        <p className="muted">Rollback controls require the model:rollback permission (typically admin).</p>
      </section>
    )
  }

  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Rollback</p>
          <h2>Active version pointer</h2>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        Metadata-only rollback. Requires <code>enable_file_writes</code> on the file registry in server config.
      </p>
      <div style={{ display: 'grid', gap: 8, maxWidth: 420 }}>
        <input aria-label="Model key" className="text-input" value={modelKey} onChange={(e) => setModelKey(e.target.value)} />
        <input aria-label="Model version" className="text-input" value={version} onChange={(e) => setVersion(e.target.value)} />
        <textarea className="text-input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Audit reason (required)" />
        <button type="button" className="primary-button" onClick={submit}>Execute rollback</button>
      </div>
      {msg && <pre style={{ marginTop: 10, fontSize: 11 }}>{msg}</pre>}
    </section>
  )
}
