import AlertCard from '../alerts/AlertCard'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'

export default function AlertFeed({
  alerts = [],
  loading,
  error,
  stale,
  selectedAlertId,
  actionError,
  onRetry,
  onSelect,
  onAcknowledge,
  onResolve,
  onEscalate,
  busy,
}) {
  return (
    <section className="panel alert-feed">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Live Alert Feed</p>
          <h2>Operator Queue</h2>
        </div>
        {stale && <span className="stale-pill">stale</span>}
      </div>
      {loading && <LoadingState label="Loading alerts" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {actionError && <ErrorState message={actionError} />}
      {!loading && !error && alerts.length === 0 && <EmptyState message="No active alerts in runtime." />}
      <div className="stack-list">
        {alerts.map(alert => (
          <AlertCard
            key={alert.alert_id}
            alert={alert}
            selected={selectedAlertId === alert.alert_id}
            onSelect={onSelect}
            onAcknowledge={onAcknowledge}
            onResolve={onResolve}
            onEscalate={onEscalate}
            busy={busy}
          />
        ))}
      </div>
    </section>
  )
}
