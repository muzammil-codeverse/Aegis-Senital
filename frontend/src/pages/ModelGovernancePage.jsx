import React from 'react'
import { useModelGovernance } from '../hooks/useModelGovernance.js'
import ModelRegistryPanel from '../components/model-governance/ModelRegistryPanel.jsx'
import ModelLimitationsPanel from '../components/model-governance/ModelLimitationsPanel.jsx'
import ModelDriftPanel from '../components/model-governance/ModelDriftPanel.jsx'
import ModelPromotionPolicyPanel from '../components/model-governance/ModelPromotionPolicyPanel.jsx'
import ModelRollbackPanel from '../components/model-governance/ModelRollbackPanel.jsx'

export default function ModelGovernancePage() {
  const gov = useModelGovernance()

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Governance</p>
            <h1>Model governance</h1>
          </div>
          <button type="button" className="text-button" onClick={() => gov.runValidate()}>
            Run validate
          </button>
        </div>
        {gov.loading && <p className="muted">Loading…</p>}
        {gov.error && <p className="muted" style={{ color: '#f85149' }}>{gov.error}</p>}
        {gov.validation && (
          <pre style={{ fontSize: 11, background: '#0d1117', padding: 12, borderRadius: 6 }}>
            {JSON.stringify(gov.validation, null, 2)}
          </pre>
        )}
      </section>
      <ModelRegistryPanel entries={gov.registry} />
      <ModelLimitationsPanel items={gov.limitations} />
      <ModelPromotionPolicyPanel policy={gov.policy} />
      <ModelDriftPanel loadDrift={gov.loadDrift} />
      <ModelRollbackPanel />
    </div>
  )
}
