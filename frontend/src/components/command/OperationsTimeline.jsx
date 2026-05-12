import { useEffect, useMemo, useState } from 'react'
import { getAlerts } from '../../api/alertsApi'
import { listCases } from '../../api/caseApi'
import { getFusionTimeline } from '../../api/droneFusionApi'
import { listMissions } from '../../api/droneMissionApi'
import { investigationApi } from '../../api/investigationApi'
import { listUploadedVideoSessions } from '../../api/uploadedVideoApi'
import { useAuth } from '../../hooks/useAuth'
import { formatDateTime } from '../../utils/time'

function asTimestamp(value) {
  const ts = Date.parse(value || '')
  return Number.isFinite(ts) ? ts : 0
}

function normalizeFusionTimeline(payload) {
  const source = payload?.item?.events || payload?.item?.timeline || payload?.events || payload?.timeline || payload?.items || []
  return Array.isArray(source) ? source : []
}

export default function OperationsTimeline({ limit = 14 }) {
  const auth = useAuth()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      const rows = []
      try {
        const tasks = []
        if (auth.hasPermission('alert:read')) tasks.push(getAlerts({ limit: 8 }).then(result => ['alerts', result.items || []]))
        if (auth.hasPermission('case:read')) tasks.push(listCases({ limit: 8 }).then(result => ['cases', result.items || []]))
        if (auth.hasPermission('drone:read')) tasks.push(listMissions({ limit: 8 }).then(result => ['missions', result.items || []]))
        if (auth.hasPermission('drone_fusion:read')) tasks.push(getFusionTimeline({}).then(result => ['fusion', normalizeFusionTimeline(result)]))
        if (auth.hasPermission('uploaded_video:read')) tasks.push(listUploadedVideoSessions().then(result => ['uploaded', result.items || []]))
        if (auth.hasPermission('investigation:read')) tasks.push(investigationApi.listHypotheses({ limit: 8 }).then(result => ['investigation', result.items || []]))
        const settled = await Promise.allSettled(tasks)

        for (const result of settled) {
          if (result.status !== 'fulfilled') continue
          const [kind, payload] = result.value
          if (kind === 'alerts') {
            payload.forEach(item => rows.push({
              key: `alert:${item.alert_id}`,
              source: 'Alert',
              title: item.title || item.alert_id,
              detail: item.description || 'Operational alert requires operator review.',
              route: 'alerts',
              timestamp: item.updated_at || item.created_at,
            }))
          }
          if (kind === 'cases') {
            payload.forEach(item => rows.push({
              key: `case:${item.case_id}`,
              source: 'Case',
              title: item.title || item.case_id,
              detail: item.description || 'Case event recorded.',
              route: 'cases',
              timestamp: item.updated_at || item.created_at,
            }))
          }
          if (kind === 'missions') {
            payload.forEach(item => rows.push({
              key: `mission:${item.mission_id}`,
              source: 'Drone Mission',
              title: item.name || item.mission_id,
              detail: `Simulated mission ${item.status || 'status unknown'}.`,
              route: 'drone-operations',
              timestamp: item.updated_at || item.created_at,
            }))
          }
          if (kind === 'fusion') {
            payload.forEach((item, index) => rows.push({
              key: `fusion:${item.correlation_id || item.event_id || index}`,
              source: 'Fusion',
              title: item.title || item.event_type || item.correlation_id || 'Fusion event',
              detail: item.summary || item.detail || 'Candidate cross-source observation updated.',
              route: 'drone-fusion',
              timestamp: item.timestamp || item.updated_at || item.created_at,
            }))
          }
          if (kind === 'uploaded') {
            payload.forEach(item => rows.push({
              key: `uploaded:${item.session_id}`,
              source: 'Uploaded Video',
              title: item.filename || item.session_id,
              detail: `Uploaded video status: ${item.status || 'unknown'}.`,
              route: 'uploaded-video-analysis',
              timestamp: item.updated_at || item.created_at,
            }))
          }
          if (kind === 'investigation') {
            payload.forEach(item => rows.push({
              key: `investigation:${item.hypothesis_id}`,
              source: 'Investigation',
              title: item.title || item.hypothesis_id,
              detail: item.summary || 'Evidence-backed hypothesis queued for operator review.',
              route: 'investigation',
              timestamp: item.updated_at || item.created_at,
            }))
          }
        }

        rows.sort((a, b) => asTimestamp(b.timestamp) - asTimestamp(a.timestamp))
        if (!cancelled) setItems(rows.slice(0, limit))
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Failed to load operations timeline')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    const timer = window.setInterval(load, 30000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [auth.hasPermission, limit])

  const emptyMessage = useMemo(() => {
    if (loading) return 'Loading operations timeline...'
    if (error) return error
    return 'No operational events are currently visible for your role.'
  }, [error, loading])

  return (
    <section className="panel command-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Operational Review</p>
          <h2>Tactical Operations Timeline</h2>
        </div>
      </div>
      {items.length === 0 ? (
        <p className="muted">{emptyMessage}</p>
      ) : (
        <div className="operations-timeline">
          {items.map(item => (
            <article key={item.key} className="timeline-event-card">
              <div className="timeline-event-card__meta">
                <span className="state-chip">{item.source}</span>
                <span>{item.timestamp ? formatDateTime(item.timestamp) : 'Timestamp unavailable'}</span>
              </div>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              <button type="button" className="text-button" onClick={() => { window.location.hash = item.route }}>
                Open detail
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
