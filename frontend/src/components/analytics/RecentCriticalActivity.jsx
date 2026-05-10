import { formatDistanceToNowStrict } from 'date-fns'
import EmptyState from '../common/EmptyState'

function asDate(value) {
  const numeric = Number(value)
  if (Number.isFinite(numeric) && String(value).trim() !== '') {
    return new Date(numeric < 10_000_000_000 ? numeric * 1000 : numeric)
  }
  return new Date(value)
}

function buildActivityFeed({ overview, cameraRisk, anomalyTrends, identitySummary, openVocabSummary }) {
  const items = []
  ;(cameraRisk || []).slice(0, 4).forEach(item => {
    if (!item.last_event_time && item.risk_score <= 0) return
    items.push({
      id: `camera-${item.camera_id}`,
      title: `${item.camera_id} elevated to ${item.review_priority} review priority`,
      detail: `${item.critical_event_count} critical events, ${item.open_case_count} open cases, score ${item.risk_score.toFixed(1)}`,
      timestamp: item.last_event_time,
    })
  })
  if ((anomalyTrends?.critical_anomalies || 0) > 0) {
    items.push({
      id: 'anomaly-summary',
      title: 'Critical anomaly windows require review',
      detail: `${anomalyTrends.critical_anomalies} critical windows and ${anomalyTrends.false_positive_feedback_total || 0} false-positive feedback entries`,
      timestamp: anomalyTrends?.timeseries?.[anomalyTrends.timeseries.length - 1]?.bucket_end,
    })
  }
  if ((identitySummary?.review_required_matches || 0) > 0) {
    items.push({
      id: 'identity-review',
      title: 'Identity review queue remains active',
      detail: `${identitySummary.review_required_matches} possible matches require operator review`,
      timestamp: identitySummary?.recent_matches?.[0]?.matched_at,
    })
  }
  if ((openVocabSummary?.threat_hits || 0) > 0) {
    items.push({
      id: 'open-vocab',
      title: 'Open-vocabulary detections recorded',
      detail: `${openVocabSummary.threat_hits} hits across ${openVocabSummary.total_scans || 0} scans`,
      timestamp: openVocabSummary?.recent_results?.[0]?.created_at,
    })
  }
  if (!items.length && overview) {
    items.push({
      id: 'empty-overview',
      title: 'No recent critical activity',
      detail: 'Stored analytics data does not currently show critical event concentration in the selected window.',
      timestamp: null,
    })
  }
  return items
}

export default function RecentCriticalActivity(props) {
  const items = buildActivityFeed(props)

  return (
    <section className="panel analytics-panel analytics-span-5">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Recent Critical Activity</p>
          <h2>Review Feed</h2>
        </div>
        <span className="count-pill">{items.length}</span>
      </div>
      {!items.length ? <EmptyState message="No recent activity was available for this feed." /> : (
        <ol className="analytics-feed-list">
          {items.map(item => (
            <li key={item.id} className="analytics-feed-item">
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              <span>{item.timestamp ? formatDistanceToNowStrict(asDate(item.timestamp), { addSuffix: true }) : 'Current analytics window'}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
