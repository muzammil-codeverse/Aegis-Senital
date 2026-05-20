import { useMemo, useState } from 'react'
import CrossSourceCorrelationPanel from '../components/drone-fusion/CrossSourceCorrelationPanel'
import FusionConfidenceBreakdown from '../components/drone-fusion/FusionConfidenceBreakdown'
import FusionMapOverlay from '../components/drone-fusion/FusionMapOverlay'
import FusionObservationTable from '../components/drone-fusion/FusionObservationTable'
import FusionOverviewPanel from '../components/drone-fusion/FusionOverviewPanel'
import FusionReviewControls from '../components/drone-fusion/FusionReviewControls'
import FusionSafetyBadge from '../components/drone-fusion/FusionSafetyBadge'
import FusionTimeline from '../components/drone-fusion/FusionTimeline'
import HandoffSuggestionPanel from '../components/drone-fusion/HandoffSuggestionPanel'
import CommandPageHeader from '../components/layout/CommandPageHeader'
import CommandSection from '../components/layout/CommandSection'
import { useDroneFusion } from '../hooks/useDroneFusion'
import { useDroneMissions } from '../hooks/useDroneMissions'

function countByStatus(items) {
  return items.reduce((acc, item) => {
    const status = String(item.review_status || 'pending').toLowerCase()
    acc[status] = (acc[status] || 0) + 1
    return acc
  }, {})
}

export default function DroneFusionPage() {
  const [caseId, setCaseId] = useState('')
  const [activeTab, setActiveTab] = useState('overview')
  const fusion = useDroneFusion({ caseId: caseId || undefined })
  const missions = useDroneMissions()

  const tabs = ['overview', 'observations', 'correlations', 'handoffs', 'timeline', 'map']
  const counts = useMemo(() => countByStatus(fusion.correlations || []), [fusion.correlations])
  const firstPending = useMemo(
    () => (fusion.correlations || []).find(item => String(item.review_status || 'pending').toLowerCase() === 'pending') || null,
    [fusion.correlations],
  )
  const sourceSummary = useMemo(() => {
    const summary = {}
    for (const item of fusion.observations || []) {
      const key = item.source_type || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    }
    return Object.entries(summary)
      .map(([key, value]) => `${key}: ${value}`)
      .join(' | ')
  }, [fusion.observations])

  return (
    <div className="page-stack">
      <CommandPageHeader
        eyebrow="Drone Operations"
        title="Drone Fusion"
        description="Cross-source review workspace with mission context for simulated drone observations and fixed camera events. All outputs remain candidate observations until operator review."
        badges={[
          'Candidate cross-source observation',
          'Simulated drone source badges',
          'Operator review required',
        ]}
        actions={(
          <div className="button-row">
            <input
              aria-label="Filter by case ID"
              value={caseId}
              onChange={event => setCaseId(event.target.value)}
              placeholder="Filter by case ID"
            />
            <button type="button" className="command-action-button" onClick={fusion.fetchAll} disabled={fusion.loading}>
              Refresh
            </button>
            {fusion.observations.length === 0 && (
              <button
                type="button"
                className="command-action-button"
                onClick={() => { window.location.hash = 'exhibition-demo' }}
              >
                Start Exhibition Demo
              </button>
            )}
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'map-operations' }}>
              Open map overlays
            </button>
          </div>
        )}
      />

      <div className="command-summary-grid">
        <article className="command-summary-card">
          <span>Source-pair summary</span>
          <strong>{fusion.observations.length}</strong>
          <p>{sourceSummary || (fusion.observations.length === 0 ? 'Synthetic scenario fusion ready — start exhibition demo to generate live observations.' : 'No authorized observations are currently visible.')}</p>
        </article>
        <article className="command-summary-card">
          <span>Pending reviews</span>
          <strong>{counts.pending || 0}</strong>
          <p>Pending correlations require an operator decision before downstream use.</p>
        </article>
        <article className="command-summary-card">
          <span>Accepted / rejected</span>
          <strong>{counts.accepted || 0} / {counts.rejected || 0}</strong>
          <p>Accepted items remain evidence-backed hypotheses, not identity confirmation.</p>
        </article>
        <article className="command-summary-card">
          <span>Fusion WebSocket</span>
          <strong>{fusion.wsStatus}</strong>
          <p>{fusion.error || `${fusion.reconnectCount} reconnect attempt(s) recorded.`}</p>
        </article>
      </div>

      <CommandSection
        eyebrow="Safety Language"
        title="Safe wording"
        description="This workspace uses safe language only and keeps cross-source outputs in a reviewable, non-final state."
        actions={<FusionSafetyBadge simulated operatorReviewRequired />}
      >
        <div className="button-row">
          <span className="state-chip">Mission context</span>
          <span className="state-chip">Simulated drone observation</span>
          <span className="state-chip">Possible movement path</span>
          <span className="state-chip">Evidence-backed hypothesis</span>
          <span className="state-chip">Insufficient data handling</span>
        </div>
      </CommandSection>

      <div className="command-two-column">
        <CommandSection eyebrow="Review Queue" title="Priority correlation review" description="Review controls are attached to pending items only.">
          {firstPending ? (
            <div className="stack-list">
              <article className="case-subcard">
                <div className="alert-card-header">
                  <strong>{firstPending.correlation_id}</strong>
                  <span className="state-chip">{firstPending.review_status || 'pending'}</span>
                </div>
                <p className="drawer-description">
                  Case {firstPending.case_id || 'n/a'} | confidence {(Number(firstPending.confidence || 0) * 100).toFixed(1)}%
                </p>
                <FusionConfidenceBreakdown breakdown={firstPending.confidence_breakdown} confidence={Number(firstPending.confidence || 0)} />
                <div style={{ marginTop: 10 }}>
                  <FusionReviewControls
                    correlationId={firstPending.correlation_id}
                    reviewStatus={firstPending.review_status}
                    onReview={fusion.reviewCorrelation}
                  />
                </div>
              </article>
            </div>
          ) : (
            <p className="muted">No pending fusion reviews are currently visible.</p>
          )}
        </CommandSection>
        <CommandSection eyebrow="Map Link" title="Spatial overlay handoff" description="Open the map overlay when you need to compare route geometry, camera coverage, and fusion output.">
          <div className="drawer-grid case-health-grid">
            <span>Observations</span><strong>{fusion.observations.length}</strong>
            <span>Correlations</span><strong>{fusion.correlations.length}</strong>
            <span>Handoffs</span><strong>{fusion.handoffs.length}</strong>
            <span>Timeline events</span><strong>{Array.isArray(fusion.timeline?.items) ? fusion.timeline.items.length : Array.isArray(fusion.timeline?.events) ? fusion.timeline.events.length : 0}</strong>
          </div>
          <div className="button-row">
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'map-operations' }}>
              View on map
            </button>
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-operations' }}>
              Open drone hub
            </button>
          </div>
        </CommandSection>
      </div>

      <div className="button-row" style={{ marginTop: 4, marginBottom: 4 }}>
        {tabs.map(tab => (
          <button
            key={tab}
            type="button"
            className={`command-action-button ${activeTab === tab ? '' : 'subtle'}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {activeTab === 'overview' ? (
        <FusionOverviewPanel observations={fusion.observations} correlations={fusion.correlations} handoffs={fusion.handoffs} />
      ) : null}
      {activeTab === 'observations' ? (
        <FusionObservationTable observations={fusion.observations} />
      ) : null}
      {activeTab === 'correlations' ? (
        <CrossSourceCorrelationPanel
          correlations={fusion.correlations}
          onReview={fusion.reviewCorrelation}
          onCorrelate={() => fusion.correlate({ case_id: caseId || undefined })}
          onCorrelateMission={() => fusion.correlate({ case_id: caseId || undefined, source_types: ['drone_simulation', 'fixed_camera'] })}
          onRunHandoffDemo={() => {
            const sessionId = missions?.activeSession?.session_id
            if (!sessionId) {
              window.location.hash = 'drone-mission-planner'
              return
            }
            fusion.correlate({ case_id: caseId || undefined, source_types: ['drone_simulation', 'fixed_camera'], event_id: sessionId })
          }}
          loading={fusion.loading}
        />
      ) : null}
      {activeTab === 'handoffs' ? (
        <HandoffSuggestionPanel handoffs={fusion.handoffs} />
      ) : null}
      {activeTab === 'timeline' ? (
        <FusionTimeline timeline={fusion.timeline} />
      ) : null}
      {activeTab === 'map' ? (
        <FusionMapOverlay correlations={fusion.correlations} handoffs={fusion.handoffs} observations={fusion.observations} />
      ) : null}
    </div>
  )
}
