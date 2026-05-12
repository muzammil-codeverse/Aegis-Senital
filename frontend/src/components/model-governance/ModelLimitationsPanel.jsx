import React from 'react'

export default function ModelLimitationsPanel({ items = [] }) {
  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Limitations</p>
          <h2>Known limitation</h2>
        </div>
      </div>
      <ul style={{ paddingLeft: 18, color: '#d1d5db', fontSize: 13 }}>
        {items.map((it) => (
          <li key={it.model_id} style={{ marginBottom: 10 }}>
            <strong>{it.model_id}</strong>
            <ul style={{ marginTop: 4 }}>
              {(it.known_limitations || []).map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  )
}
