import IncidentPanel from '../components/dashboard/IncidentPanel'

export default function IncidentsPage({ incidentState }) {
  return (
    <div className="page-grid single-column">
      <IncidentPanel
        incidents={incidentState.incidents}
        selectedIncident={incidentState.selectedIncident}
        selectedIncidentId={incidentState.selectedIncident?.incident_id || incidentState.selectedIncident?.id}
        loading={incidentState.loading}
        detailLoading={incidentState.detailLoading}
        error={incidentState.error}
        detailError={incidentState.detailError}
        stale={incidentState.stale}
        onRetry={incidentState.refresh}
        onSelect={incidentState.selectIncident}
      />
    </div>
  )
}
