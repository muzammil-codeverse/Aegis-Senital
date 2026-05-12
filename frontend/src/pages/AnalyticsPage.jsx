import { useState } from 'react'
import AnalyticsCommandCenter from '../components/analytics/AnalyticsCommandCenter'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'

export default function AnalyticsPage() {
  const auth = useAuth()
  const [initialCameraId] = useState(() => {
    const value = window.sessionStorage.getItem('aegis.analytics.camera') || ''
    if (value) window.sessionStorage.removeItem('aegis.analytics.camera')
    return value
  })
  const analytics = useAnalytics({
    enabled: auth.hasPermission('analytics:read'),
    initialFilters: { camera_id: initialCameraId },
  })

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
        </div>
        <p className="muted">
          Use the uploaded-video workflow to replay evidence through the same analytics pipeline, then compare event counts and case output from this dashboard.
        </p>
      </section>
      <AnalyticsCommandCenter analytics={analytics} canExport={auth.hasPermission('analytics:export')} />
    </>
  )
}
