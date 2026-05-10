import { useEffect, useMemo, useState } from 'react'
import ProtectedRoute from './components/auth/ProtectedRoute'
import SessionExpiredBanner from './components/auth/SessionExpiredBanner'
import AppShell from './components/layout/AppShell'
import { useAlerts } from './hooks/useAlerts'
import { useAuth } from './hooks/useAuth'
import { useCases } from './hooks/useCases'
import { useIncidents } from './hooks/useIncidents'
import { useMetrics } from './hooks/useMetrics'
import { useSystemHealth } from './hooks/useSystemHealth'
import { useWebSocketAlerts } from './hooks/useWebSocketAlerts'
import AlertsPage from './pages/AlertsPage'
import AuditLogPage from './pages/AuditLogPage'
import AnalyticsPage from './pages/AnalyticsPage'
import CasesPage from './pages/CasesPage'
import Dashboard from './pages/Dashboard'
import ForensicsPage from './pages/ForensicsPage'
import IdentityPage from './pages/IdentityPage'
import IncidentsPage from './pages/IncidentsPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import SystemHealthPage from './pages/SystemHealthPage'

const VALID_PAGES = new Set([
  'dashboard', 'alerts', 'incidents', 'cases', 'system', 'forensics',
  'identities', 'watchlist', 'models', 'audit', 'analytics', 'security', 'login',
])

const PAGE_PERMISSIONS = {
  dashboard: 'camera:read',
  alerts: 'alert:read',
  incidents: 'incident:read',
  cases: 'case:read',
  analytics: 'analytics:read',
  system: 'metrics:read',
  forensics: 'forensics:read',
  identities: 'identity:read',
  watchlist: 'watchlist:read',
  models: 'model:read',
  audit: 'audit:read',
  security: 'admin',
}

export default function App() {
  const auth = useAuth()
  if (auth.loading) {
    return (
      <main className="login-screen">
        <div className="login-panel">
          <p className="eyebrow">Aegis Sentinel</p>
          <h1>Loading Session</h1>
        </div>
      </main>
    )
  }
  if (!auth.authenticated) {
    return (
      <>
        <SessionExpiredBanner />
        <LoginPage />
      </>
    )
  }
  return <AuthenticatedApp />
}

function AuthenticatedApp() {
  const auth = useAuth()
  const [currentPage, setCurrentPage] = useState(pageFromHash())
  const alertState = useAlerts()
  const incidentState = useIncidents()
  const caseState = useCases({ enabled: auth.hasPermission('case:read') })
  const metricsState = useMetrics()
  const websocketState = useWebSocketAlerts()
  const health = useSystemHealth(metricsState.metrics, metricsState.error, metricsState.stale)

  useEffect(() => {
    function handleHashChange() {
      setCurrentPage(pageFromHash())
    }
    window.addEventListener('hashchange', handleHashChange)
    if (pageFromHash() === 'login') {
      window.location.hash = ''
      setCurrentPage('dashboard')
    }
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const sharedProps = useMemo(() => ({
    alertState,
    incidentState,
    caseState,
    metricsState,
    websocketState,
    health,
  }), [alertState, caseState, health, incidentState, metricsState, websocketState])

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
      <ProtectedRoute permission={PAGE_PERMISSIONS[currentPage]}>
        {renderPage(currentPage, sharedProps)}
      </ProtectedRoute>
    </AppShell>
  )
}

function renderPage(page, props) {
  if (page === 'alerts') return <AlertsPage {...props} />
  if (page === 'incidents') return <IncidentsPage {...props} />
  if (page === 'cases') return <CasesPage caseState={props.caseState} />
  if (page === 'analytics') return <AnalyticsPage />
  if (page === 'system') return <SystemHealthPage {...props} />
  if (page === 'forensics') return <ForensicsPage {...props} />
  if (page === 'identities') return <IdentityPage />
  if (page === 'watchlist') return <IdentityPage />
  if (page === 'models') return <ModelsPage />
  if (page === 'audit') return <AuditLogPage />
  if (page === 'security') return <AuditLogPage mode="users" />
  return <Dashboard {...props} />
}

function pageFromHash() {
  const page = window.location.hash.replace('#', '') || 'dashboard'
  return VALID_PAGES.has(page) ? page : 'dashboard'
}
