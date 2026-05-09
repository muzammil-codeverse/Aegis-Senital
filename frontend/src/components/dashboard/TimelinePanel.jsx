import { useState } from 'react'
import { getTimeline } from '../../api/timelineApi'
import { normalizeError } from '../../api/client'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatPercent } from '../../utils/formatters'
import { formatTimestamp } from '../../utils/time'

export default function TimelinePanel({ defaultTrackId = '' }) {
  const [trackId, setTrackId] = useState(defaultTrackId)
  const [timeline, setTimeline] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!trackId) return
    setLoading(true)
    setError(null)
    try {
      const response = await getTimeline(trackId)
      setTimeline(response.item)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }

  const events = Array.isArray(timeline?.events) ? timeline.events : []
  const transitions = Array.isArray(timeline?.camera_transitions) ? timeline.camera_transitions : []
  const riskTimeline = Array.isArray(timeline?.risk_timeline) ? timeline.risk_timeline : []

  return (
    <section className="panel timeline-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Forensic Preview</p>
          <h2>Track Timeline</h2>
        </div>
        <form className="inline-form" onSubmit={handleSubmit}>
          <input value={trackId} onChange={event => setTrackId(event.target.value)} placeholder="track id" aria-label="Track ID" />
          <button type="submit">Fetch</button>
        </form>
      </div>
      {loading && <LoadingState label="Loading timeline" />}
      {error && <ErrorState message={error} />}
      {!loading && !error && !timeline && <EmptyState message="Enter a track ID to fetch forensic timeline metadata." />}
      {timeline && (
        <div className="timeline-sections">
          <div>
            <h3>Events</h3>
            {events.length === 0 ? <EmptyState message="No events for this track." /> : (
              <ol className="timeline-list">
                {events.map((event, index) => (
                  <li key={`${event.event_id || index}`}>
                    <span>{formatTimestamp(event.timestamp)}</span>
                    <strong>{event.event_type || 'event'}</strong>
                    <em>{event.camera_id || event.camera_ids?.[0] || 'camera N/A'}</em>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <h3>Camera Transitions</h3>
            {transitions.length === 0 ? <EmptyState message="No camera transitions." /> : (
              <ol className="timeline-list">
                {transitions.map((transition, index) => (
                  <li key={`${transition.from}-${transition.to}-${index}`}>
                    <span>{formatTimestamp(transition.timestamp)}</span>
                    <strong>{transition.from || 'N/A'} to {transition.to || 'N/A'}</strong>
                    <em>handoff</em>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <h3>Risk Timeline</h3>
            {riskTimeline.length === 0 ? <EmptyState message="No risk timeline." /> : (
              <ol className="timeline-list">
                {riskTimeline.map((risk, index) => (
                  <li key={`${risk.timestamp}-${index}`}>
                    <span>{formatTimestamp(risk.timestamp)}</span>
                    <strong>{formatPercent(risk.risk_score)}</strong>
                    <em>risk score</em>
                  </li>
                ))}
              </ol>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
