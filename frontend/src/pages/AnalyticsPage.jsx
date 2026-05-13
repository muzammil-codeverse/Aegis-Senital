import { useEffect, useState } from 'react'
import AnalyticsCommandCenter from '../components/analytics/AnalyticsCommandCenter'
import { getGeofences, getGisHeatmap } from '../api/gisApi'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { useDroneSimulation } from '../hooks/useDroneSimulation'

export default function AnalyticsPage() {
  const auth = useAuth()
  const drone = useDroneSimulation({ enabled: auth.hasPermission('drone:read'), pollMs: 10000 })
  const [gisSnap, setGisSnap] = useState(null)
  const [initialCameraId] = useState(() => {
    const value = window.sessionStorage.getItem('aegis.analytics.camera') || ''
    if (value) window.sessionStorage.removeItem('aegis.analytics.camera')
    return value
  })
  const analytics = useAnalytics({
    enabled: auth.hasPermission('analytics:read'),
    initialFilters: { camera_id: initialCameraId },
  })

  useEffect(() => {
    if (!auth.hasPermission('gis:read')) return undefined
    let cancelled = false
    ;(async () => {
      try {
        const [h, g] = await Promise.all([getGisHeatmap(), getGeofences()])
        if (!cancelled) setGisSnap({ heatmapCells: h.count, geofences: g.count })
      } catch {
        if (!cancelled) setGisSnap(null)
      }
    })()
    return () => { cancelled = true }
  }, [auth])

  return (
    <>
      <section className="panel analytics-preview-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Uploaded Video</p>
            <h2>Offline Validation Workflow</h2>
          </div>
          <button type="button" className="text-button" onClick={() => { window.location.hash = 'uploaded-video-analysis' }}>
            Open Uploaded Video Analysis
          </button>
          <button type="button" className="text-button" onClick={() => { window.location.hash = 'model-governance' }}>
            Model governance
          </button>
          {auth.hasPermission('drone:read') ? (
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-simulation' }}>
              Drone simulation
            </button>
          ) : null}
          {auth.hasPermission('gis:read') ? (
            <button type="button" className="text-button" onClick={() => { window.location.hash = 'map-operations' }}>
              Map / GIS
            </button>
          ) : null}
        </div>
        {gisSnap ? (
          <p className="muted" style={{ marginTop: 8 }}>
            GIS snapshot: heatmap cells {gisSnap.heatmapCells}, geofences {gisSnap.geofences}. Open Map for highest-risk area and camera coverage context.
          </p>
        ) : null}
        {auth.hasPermission('drone:read') ? (
          <p className="muted" style={{ marginTop: 8 }}>
            Drone simulation status: {drone.status?.health?.status || 'unknown'} with {drone.stats.framesProcessed} processed frames and {drone.stats.events} detected events from the simulated aerial source.
          </p>
        ) : null}
        {auth.hasPermission('drone:read') ? (
          <div className="metric-strip" style={{ marginTop: 10 }}>
            <article className="metric-tile"><span>Drone runtime</span><strong>{drone.runtimeStatus?.selected_runtime || 'unknown'}</strong></article>
            <article className="metric-tile"><span>Active mission</span><strong>{drone.status?.session?.status || 'idle'}</strong></article>
            <article className="metric-tile"><span>Frames processed</span><strong>{drone.stats.framesProcessed}</strong></article>
            <article className="metric-tile"><span>Detections generated</span><strong>{drone.stats.events}</strong></article>
            <article className="metric-tile"><span>Fusion correlations</span><strong>{analytics?.data?.dashboard?.drone_fusion_correlations ?? analytics?.data?.summary?.drone_fusion_correlations ?? 0}</strong></article>
            <article className="metric-tile"><span>Feed health</span><strong>{drone.status?.health?.status || 'unknown'}</strong></article>
          </div>
        ) : null}
        <p className="muted">
          Use the uploaded-video workflow to replay evidence through the same analytics pipeline, then compare event counts and case output from this dashboard.
        </p>
      </section>
      <AnalyticsCommandCenter analytics={analytics} canExport={auth.hasPermission('analytics:export')} />
    </>
  )
}
