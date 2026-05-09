import IncidentCard from '../incidents/IncidentCard'
import IncidentTimeline from '../incidents/IncidentTimeline'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'

export default function IncidentPanel({
  incidents = [],
  selectedIncident,
  selectedIncidentId,
  loading,
  detailLoading,
  error,
  detailError,
  stale,
  onRetry,
  onSelect,
}) {
  return (
    <section className="panel incident-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Incident Lifecycle</p>
          <h2>Active Incidents</h2>
        </div>
        {stale && <span className="stale-pill">stale</span>}
      </div>
      {loading && <LoadingState label="Loading incidents" />}
      {error && <ErrorState message={error} onRetry={onRetry} />}
      {!loading && !error && incidents.length === 0 && <EmptyState message="No runtime incidents are active." />}
      <div className="incident-layout">
        <div className="stack-list">
          {incidents.map(incident => {
            const incidentId = incident.incident_id || incident.id
            return (
              <IncidentCard
                key={incidentId}
                incident={incident}
                selected={selectedIncidentId === incidentId}
                onSelect={onSelect}
              />
            )
          })}
        </div>
        <div className="incident-detail">
          {detailLoading && <LoadingState label="Loading incident detail" />}
          {detailError && <ErrorState message={detailError} />}
          {!detailLoading && <IncidentTimeline incident={selectedIncident} />}
        </div>
      </div>
    </section>
  )
}
