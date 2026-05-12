import { useState } from 'react'
import CrossSourceCorrelationPanel from '../components/drone-fusion/CrossSourceCorrelationPanel'
import FusionMapOverlay from '../components/drone-fusion/FusionMapOverlay'
import FusionObservationTable from '../components/drone-fusion/FusionObservationTable'
import FusionOverviewPanel from '../components/drone-fusion/FusionOverviewPanel'
import FusionTimeline from '../components/drone-fusion/FusionTimeline'
import HandoffSuggestionPanel from '../components/drone-fusion/HandoffSuggestionPanel'
import { useDroneFusion } from '../hooks/useDroneFusion'

export default function DroneFusionPage() {
  const [caseId, setCaseId] = useState('')
  const [activeTab, setActiveTab] = useState('overview')

  const {
    observations,
    correlations,
    handoffs,
    timeline,
    loading,
    error,
    correlate,
    reviewCorrelation,
    fetchAll,
  } = useDroneFusion({ caseId: caseId || undefined })

  const tabs = ['overview', 'observations', 'correlations', 'handoffs', 'timeline', 'map']

  return (
    <div style={{ padding: 16, color: '#f9fafb', fontFamily: 'monospace', maxWidth: 1200 }}>
      <h2 style={{ marginBottom: 4 }}>Drone + Fixed Camera Fusion</h2>
      <div style={{ fontSize: 12, color: '#f59e0b', marginBottom: 12 }}>
        All results are candidate cross-source observations. No identity confirmation. Operator review required.
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          value={caseId}
          onChange={e => setCaseId(e.target.value)}
          placeholder="Filter by Case ID (optional)"
          style={{ padding: '4px 8px', background: '#1f2937', border: '1px solid #374151', color: '#f9fafb', borderRadius: 4, fontSize: 13 }}
        />
        <button onClick={fetchAll} disabled={loading}
          style={{ background: '#374151', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: 6, cursor: 'pointer' }}>
          Refresh
        </button>
        {loading && <span style={{ color: '#9ca3af', fontSize: 12 }}>Loading…</span>}
        {error && <span style={{ color: '#ef4444', fontSize: 12 }}>{error}</span>}
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
        {tabs.map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 13,
              background: activeTab === tab ? '#1d4ed8' : '#1f2937',
              color: activeTab === tab ? '#fff' : '#9ca3af',
            }}>
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <FusionOverviewPanel observations={observations} correlations={correlations} handoffs={handoffs} />
      )}
      {activeTab === 'observations' && (
        <FusionObservationTable observations={observations} />
      )}
      {activeTab === 'correlations' && (
        <CrossSourceCorrelationPanel
          correlations={correlations}
          onReview={reviewCorrelation}
          onCorrelate={() => correlate({ case_id: caseId || undefined })}
          loading={loading}
        />
      )}
      {activeTab === 'handoffs' && (
        <HandoffSuggestionPanel handoffs={handoffs} />
      )}
      {activeTab === 'timeline' && (
        <FusionTimeline timeline={timeline} />
      )}
      {activeTab === 'map' && (
        <FusionMapOverlay correlations={correlations} handoffs={handoffs} observations={observations} />
      )}
    </div>
  )
}
