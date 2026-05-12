import { useEffect, useState } from 'react'

export default function MapFilterPanel({ value, onChange }) {
  const [local, setLocal] = useState(value || {})
  useEffect(() => {
    setLocal(value || {})
  }, [value])
  function update(patch) {
    const next = { ...local, ...patch }
    setLocal(next)
    onChange?.(next)
  }
  return (
    <div className="panel" style={{ padding: 12 }}>
      <p className="eyebrow">Filters</p>
      <div className="drawer-grid" style={{ fontSize: '0.75rem' }}>
        <span>Severity</span>
        <select value={local.severity || ''} onChange={e => update({ severity: e.target.value || undefined })}>
          <option value="">Any</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
        <span>Source</span>
        <select value={local.source_type || ''} onChange={e => update({ source_type: e.target.value || undefined })}>
          <option value="">Any</option>
          <option value="live_stream">live_stream</option>
          <option value="uploaded_video">uploaded_video</option>
          <option value="drone_simulation">drone_simulation</option>
        </select>
      </div>
    </div>
  )
}
