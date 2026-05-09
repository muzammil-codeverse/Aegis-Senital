import { useEffect, useMemo, useState } from 'react'
import AppShell from './components/layout/AppShell'
import { useAlerts } from './hooks/useAlerts'
import { useIncidents } from './hooks/useIncidents'
import { useMetrics } from './hooks/useMetrics'
import { useSystemHealth } from './hooks/useSystemHealth'
import { useWebSocketAlerts } from './hooks/useWebSocketAlerts'
import AlertsPage from './pages/AlertsPage'
import Dashboard from './pages/Dashboard'
import ForensicsPage from './pages/ForensicsPage'
import IncidentsPage from './pages/IncidentsPage'
import SystemHealthPage from './pages/SystemHealthPage'

const VALID_PAGES = new Set(['dashboard', 'alerts', 'incidents', 'system', 'forensics'])

export default function App() {
  const [currentPage, setCurrentPage] = useState(pageFromHash())
  const alertState = useAlerts()
  const incidentState = useIncidents()
  const metricsState = useMetrics()
  const websocketState = useWebSocketAlerts()
  const health = useSystemHealth(metricsState.metrics, metricsState.error, metricsState.stale)

  useEffect(() => {
    function handleHashChange() {
      setCurrentPage(pageFromHash())
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const sharedProps = useMemo(() => ({
    alertState,
    incidentState,
    metricsState,
    websocketState,
    health,
  }), [alertState, health, incidentState, metricsState, websocketState])

  function navigate(pageId) {
    window.location.hash = pageId === 'dashboard' ? '' : pageId
    setCurrentPage(pageId)
  }

  return (
    <AppShell
      currentPage={currentPage}
      onNavigate={navigate}
      metrics={metricsState.metrics}
      health={health}
      websocketStatus={websocketState.status}
      lastMessageAt={websocketState.lastMessageAt}
      reconnectCount={websocketState.reconnectCount}
    >
      {renderPage(currentPage, sharedProps)}
    </AppShell>
  )
}

function renderPage(page, props) {
  if (page === 'alerts') return <AlertsPage {...props} />
  if (page === 'incidents') return <IncidentsPage {...props} />
  if (page === 'system') return <SystemHealthPage {...props} />
  if (page === 'forensics') return <ForensicsPage {...props} />
  return <Dashboard {...props} />
}

function pageFromHash() {
  const page = window.location.hash.replace('#', '') || 'dashboard'
  return VALID_PAGES.has(page) ? page : 'dashboard'
}
