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

  return <AnalyticsCommandCenter analytics={analytics} canExport={auth.hasPermission('analytics:export')} />
}
