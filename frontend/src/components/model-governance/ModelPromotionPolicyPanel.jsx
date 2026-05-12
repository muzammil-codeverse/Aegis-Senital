import React from 'react'

export default function ModelPromotionPolicyPanel({ policy }) {
  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Policy</p>
          <h2>Promotion rules</h2>
        </div>
      </div>
      <pre style={{ fontSize: 11, background: '#0d1117', padding: 12, borderRadius: 6, overflow: 'auto' }}>
        {JSON.stringify(policy || {}, null, 2)}
      </pre>
    </section>
  )
}
