import AlertDetailDrawer from '../components/alerts/AlertDetailDrawer'
import AlertFeed from '../components/dashboard/AlertFeed'

export default function AlertsPage({ alertState, websocketState }) {
  const alerts = mergeAlerts(alertState.alerts, websocketState.alerts)
  return (
    <div className="page-grid single-column">
      <AlertFeed
        alerts={alerts}
        loading={alertState.loading}
        error={alertState.error}
        stale={alertState.stale}
        selectedAlertId={alertState.selectedAlert?.alert_id}
        actionError={alertState.actionError}
        onRetry={alertState.refresh}
        onSelect={alertState.selectAlert}
        onAcknowledge={alertState.acknowledge}
        onResolve={alertState.resolve}
        onEscalate={alertState.escalate}
        busy={alertState.actionLoading}
      />
      <AlertDetailDrawer
        open={Boolean(alertState.selectedAlert)}
        alert={alertState.selectedAlert}
        history={alertState.history}
        loading={alertState.detailLoading}
        error={alertState.actionError}
        onClose={() => alertState.selectAlert(null)}
        onAcknowledge={alertState.acknowledge}
        onResolve={alertState.resolve}
        onEscalate={alertState.escalate}
        busy={alertState.actionLoading}
      />
    </div>
  )
}

function mergeAlerts(apiAlerts, websocketAlerts) {
  const byId = new Map()
  ;[...apiAlerts, ...websocketAlerts].forEach(alert => {
    if (!alert?.alert_id) return
    byId.set(alert.alert_id, { ...byId.get(alert.alert_id), ...alert })
  })
  return [...byId.values()].sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))
}
