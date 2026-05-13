import FusionConfidenceBreakdown from './FusionConfidenceBreakdown'
import FusionReviewControls from './FusionReviewControls'
import FusionSafetyBadge from './FusionSafetyBadge'

export default function CrossSourceCorrelationPanel({
  correlations = [],
  onReview,
  onCorrelate,
  onCorrelateMission,
  onRunHandoffDemo,
  loading,
}) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>Cross-Source Correlations ({correlations.length})</h3>
        <div className="button-row">
          <button
            onClick={onCorrelate}
            disabled={loading}
            style={{ background: '#1d4ed8', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: 6, cursor: 'pointer' }}
          >
            {loading ? 'Running...' : 'Run Correlation'}
          </button>
          <button type="button" className="text-button" onClick={onCorrelateMission} disabled={loading}>
            Correlate Active Mission + Fixed Cameras
          </button>
          <button type="button" className="text-button" onClick={onRunHandoffDemo} disabled={loading}>
            Fixed Camera Handoff Demo
          </button>
        </div>
      </div>
      {!correlations.length ? <div style={{ color: '#6b7280', fontSize: 13 }}>No correlations yet.</div> : null}
      {correlations.map(corr => (
        <div key={corr.correlation_id} style={{ border: '1px solid #374151', borderRadius: 6, padding: 10, marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
            <span style={{ fontSize: 12, color: '#60a5fa' }}>{corr.source_pair?.join(' <-> ')}</span>
            <FusionSafetyBadge simulated={false} operatorReviewRequired={corr.operator_review_required} />
          </div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 6 }}>{corr.safe_summary}</div>
          <div className="button-row" style={{ marginBottom: 6 }}>
            <span className="state-chip">Mission context score: {Number(corr?.confidence_breakdown?.mission_context_score || 0).toFixed(2)}</span>
          </div>
          <FusionConfidenceBreakdown breakdown={corr.confidence_breakdown} confidence={corr.confidence} />
          <div style={{ marginTop: 8 }}>
            <FusionReviewControls
              correlationId={corr.correlation_id}
              reviewStatus={corr.review_status}
              onReview={onReview}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
