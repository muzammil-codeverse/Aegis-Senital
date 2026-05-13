import { Suspense, useEffect, useMemo, useState } from 'react'
import ProtectedRoute from './components/auth/ProtectedRoute'
import SessionExpiredBanner from './components/auth/SessionExpiredBanner'
import CommandCenterShell from './components/layout/CommandCenterShell'
import CommandErrorBoundary from './components/layout/CommandErrorBoundary'
import PageLoadingFallback from './components/layout/PageLoadingFallback'
import { useAlerts } from './hooks/useAlerts'
import { useAuth } from './hooks/useAuth'
import { useCases } from './hooks/useCases'
import { useIncidents } from './hooks/useIncidents'
import { useMetrics } from './hooks/useMetrics'
import { commandPagePermissions, commandRouteIds, getCommandPageMeta } from './navigation/commandNavigation'
import { useSystemHealth } from './hooks/useSystemHealth'
import { useWebSocketAlerts } from './hooks/useWebSocketAlerts'
import AlertsPage from './pages/AlertsPage'
import AuditLogPage from './pages/AuditLogPage'
import CasesPage from './pages/CasesPage'
import Dashboard from './pages/Dashboard'
import ForensicsPage from './pages/ForensicsPage'
import IdentityPage from './pages/IdentityPage'
import IncidentsPage from './pages/IncidentsPage'
import LoginPage from './pages/LoginPage'
import ModelsPage from './pages/ModelsPage'
import SystemHealthPage from './pages/SystemHealthPage'
import {
  LazyAnalyticsPage,
  LazyDroneFusionPage,
  LazyDroneMissionPlannerPage,
  LazyDroneOperationsHub,
  LazyDroneSimulationPage,
  LazyInvestigationWorkspacePage,
  LazyMapOperationsPage,
  LazyModelGovernancePage,
  LazyUploadedVideoAnalysisPage,
} from './routes/lazyRoutes'

const VALID_PAGES = new Set([
  ...commandRouteIds,
  'forensics',
  'watchlist',
  'models',
  'audit',
  'security',
  'login',
])

const PAGE_PERMISSIONS = {
  ...commandPagePermissions,
  forensics: 'forensics:read',
  watchlist: 'watchlist:read',
  models: 'model:read',
  audit: 'audit:read',
  security: 'admin',
}

const LEGACY_PAGE_META = {
  forensics: { id: 'forensics', label: 'Forensics', description: 'Forensic review tools' },
  watchlist: { id: 'watchlist', label: 'Watchlist', description: 'Watchlist and monitoring list' },
  models: { id: 'models', label: 'Models', description: 'Model registry and controls' },
  audit: { id: 'audit', label: 'Audit Logs', description: 'Audit trail and administrator review' },
  security: { id: 'security', label: 'Security', description: 'Administrative security controls' },
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
  const alertState = useAlerts({ enabled: auth.authenticated })
  const incidentState = useIncidents({ enabled: auth.authenticated })
  const caseState = useCases({ enabled: auth.hasPermission('case:read') })
  const metricsState = useMetrics({ enabled: auth.authenticated })
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
    <CommandCenterShell
      currentPage={currentPage}
      onNavigate={navigate}
      pageMeta={LEGACY_PAGE_META[currentPage] || getCommandPageMeta(currentPage)}
      metrics={metricsState.metrics}
      websocketStatus={websocketState.status}
      lastMessageAt={websocketState.lastMessageAt}
      reconnectCount={websocketState.reconnectCount}
    >
      <CommandErrorBoundary>
        <ProtectedRoute permission={PAGE_PERMISSIONS[currentPage]}>
          {renderPage(currentPage, sharedProps)}
        </ProtectedRoute>
      </CommandErrorBoundary>
    </CommandCenterShell>
  )
}

function renderPage(page, props) {
  // Non-heavy pages rendered directly — no lazy loading required.
  if (page === 'alerts') return <AlertsPage {...props} />
  if (page === 'incidents') return <IncidentsPage {...props} />
  if (page === 'cases') return <CasesPage caseState={props.caseState} />
  if (page === 'osint-enrichment') return <CasesPage caseState={props.caseState} />
  if (page === 'system') return <SystemHealthPage {...props} />
  if (page === 'forensics') return <ForensicsPage {...props} />
  if (page === 'identities') return <IdentityPage />
  if (page === 'watchlist') return <IdentityPage />
  if (page === 'models') return <ModelsPage />
  if (page === 'audit') return <AuditLogPage />
  if (page === 'security') return <AuditLogPage mode="users" />
  if (page === 'live-streams') return <Dashboard {...props} />

  // Heavy pages — code-split via React.lazy.  Each is wrapped in Suspense so
  // the shell stays interactive while the chunk streams in.
  if (page === 'analytics')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Analytics..." />}>
        <LazyAnalyticsPage />
      </Suspense>
    )
  if (page === 'uploaded-video-analysis')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Video Analysis..." />}>
        <LazyUploadedVideoAnalysisPage />
      </Suspense>
    )
  if (page === 'model-governance')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Model Governance..." />}>
        <LazyModelGovernancePage />
      </Suspense>
    )
  if (page === 'map-operations')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Map Operations..." />}>
        <LazyMapOperationsPage />
      </Suspense>
    )
  if (page === 'investigation')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Investigation Workspace..." />}>
        <LazyInvestigationWorkspacePage />
      </Suspense>
    )
  if (page === 'drone-operations')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Drone Operations..." />}>
        <LazyDroneOperationsHub />
      </Suspense>
    )
  if (page === 'drone-simulation')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Drone Simulation..." />}>
        <LazyDroneSimulationPage />
      </Suspense>
    )
  if (page === 'drone-mission-planner')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Mission Planner..." />}>
        <LazyDroneMissionPlannerPage />
      </Suspense>
    )
  if (page === 'drone-fusion')
    return (
      <Suspense fallback={<PageLoadingFallback label="Loading Drone Fusion..." />}>
        <LazyDroneFusionPage />
      </Suspense>
    )

  return <Dashboard {...props} />
}

function pageFromHash() {
  const page = window.location.hash.replace('#', '') || 'dashboard'
  return VALID_PAGES.has(page) ? page : 'dashboard'
}
