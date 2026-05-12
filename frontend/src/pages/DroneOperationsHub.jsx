import CommandPageHeader from '../components/layout/CommandPageHeader'
import CommandSection from '../components/layout/CommandSection'
import OperationsTimeline from '../components/command/OperationsTimeline'
import ReviewQueuePanel from '../components/command/ReviewQueuePanel'
import Tactical3DStatusScene from '../components/command/Tactical3DStatusScene'
import { useDroneFusion } from '../hooks/useDroneFusion'
import { useDroneMissions } from '../hooks/useDroneMissions'
import { useDroneSimulation } from '../hooks/useDroneSimulation'
import { useRuntimeStatus } from '../hooks/useRuntimeStatus'
import { useAuth } from '../hooks/useAuth'

function latestMission(missions) {
  return [...(missions || [])].sort((a, b) => Date.parse(b.updated_at || b.created_at || 0) - Date.parse(a.updated_at || a.created_at || 0))[0] || null
}

export default function DroneOperationsHub() {
  const auth = useAuth()
  const runtimeStatus = useRuntimeStatus()
  const drone = useDroneSimulation({ enabled: auth.hasPermission('drone:read') })
  const missions = useDroneMissions()
  const fusion = useDroneFusion()
  const mission = latestMission(missions.missions)
  const pendingFusion = (fusion.correlations || []).filter(item => String(item.review_status || 'pending').toLowerCase() === 'pending')

  if (!auth.hasPermission('drone:read')) {
    return <p className="muted">You do not have drone:read permission.</p>
  }

  return (
    <div className="page-stack">
      <CommandPageHeader
        eyebrow="Drone Operations"
        title="Drone Operations Hub"
        description="Unified simulated drone operations, mission review, telemetry, and fusion workflow summary."
        badges={[
          'Simulated aerial observation',
          'Operator review required',
          'No frontend-only telemetry',
        ]}
        actions={(
          <div className="button-row">
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'drone-simulation' }}>
              Open simulation
            </button>
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'drone-mission-planner' }}>
              Open mission planner
            </button>
            <button type="button" className="command-action-button" onClick={() => { window.location.hash = 'drone-fusion' }}>
              Open fusion
            </button>
            <button
              type="button"
              className="command-action-button"
              onClick={() => {
                if (mission?.case_id) window.sessionStorage.setItem('aegis.map.case_id', mission.case_id)
                window.location.hash = 'map-operations'
              }}
            >
              Open map
            </button>
          </div>
        )}
      />

      <div className="command-summary-grid">
        <article className="command-summary-card">
          <span>Simulation status</span>
          <strong>{drone.status?.health?.status || drone.wsStatus || 'unknown'}</strong>
          <p>{drone.status?.health?.detail || 'Live runtime status from Cosys-AirSim.'}</p>
        </article>
        <article className="command-summary-card">
          <span>Current telemetry</span>
          <strong>{drone.telemetry?.timestamp || 'No telemetry yet'}</strong>
          <p>{drone.telemetry ? `Lat ${drone.telemetry.latitude ?? 'n/a'} | Lon ${drone.telemetry.longitude ?? 'n/a'}` : 'Start or connect a simulated session to view telemetry.'}</p>
        </article>
        <article className="command-summary-card">
          <span>Mission status</span>
          <strong>{missions.activeSession?.status || mission?.status || 'No active session'}</strong>
          <p>{mission ? `${mission.name || mission.mission_id}` : 'Mission events appear after a simulated mission is created.'}</p>
        </article>
        <article className="command-summary-card">
          <span>Fusion pending reviews</span>
          <strong>{pendingFusion.length}</strong>
          <p>{pendingFusion.length > 0 ? 'Candidate cross-source observations are awaiting operator review.' : 'No pending drone fusion reviews.'}</p>
        </article>
      </div>

      <div className="command-two-column">
        <CommandSection
          eyebrow="Runtime Closure"
          title="Simulator and validation view"
          description="Live runtime health is shown here. Strict smoke status is not currently exposed by a dedicated API endpoint, so operator evidence remains the closure report and validation logs."
        >
          <div className="drawer-grid case-health-grid">
            <span>Runtime overall</span><strong>{runtimeStatus.overall}</strong>
            <span>Simulation WS</span><strong>{drone.wsStatus}</strong>
            <span>Frames processed</span><strong>{drone.stats.framesProcessed}</strong>
            <span>Events observed</span><strong>{drone.stats.events}</strong>
            <span>Runtime validation</span><strong>{runtimeStatus.byKey.droneSimulation?.summary || 'Runtime status unavailable'}</strong>
            <span>Smoke status</span><strong>Refer to runtime closure report</strong>
          </div>
        </CommandSection>
        <Tactical3DStatusScene summary="Abstract visualization of camera, mission, and fusion dependencies. This is a tactical status scene, not a real city model." />
      </div>

      <div className="command-two-column">
        <CommandSection eyebrow="Mission Control" title="Recent mission events" description="Mission lifecycle and telemetry are populated from the live simulated runtime when a session is active.">
          {missions.events.length === 0 ? (
            <p className="muted">Mission events appear after a simulated mission starts in this console.</p>
          ) : (
            <div className="stack-list">
              {missions.events.slice(0, 8).map(event => (
                <article key={event.event_id || `${event.event_type}-${event.timestamp}`} className="case-subcard">
                  <div className="alert-card-header">
                    <strong>{event.event_type || 'mission_event'}</strong>
                    <span className="state-chip">{event.timestamp || 'pending'}</span>
                  </div>
                  <p className="drawer-description">{event.detail || event.message || 'Simulated mission event recorded.'}</p>
                </article>
              ))}
            </div>
          )}
        </CommandSection>
        <CommandSection eyebrow="Fusion Review" title="Pending drone fusion items" description="Cross-source observations remain candidate observations until an operator reviews them.">
          {pendingFusion.length === 0 ? (
            <p className="muted">No pending drone fusion reviews.</p>
          ) : (
            <div className="stack-list">
              {pendingFusion.slice(0, 6).map(item => (
                <article key={item.correlation_id} className="case-subcard">
                  <div className="alert-card-header">
                    <strong>{item.correlation_id}</strong>
                    <span className="state-chip">{item.review_status || 'pending'}</span>
                  </div>
                  <p className="drawer-description">Confidence {(Number(item.confidence || 0) * 100).toFixed(1)}%. Operator review required.</p>
                  <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-fusion' }}>
                    Open fusion review
                  </button>
                </article>
              ))}
            </div>
          )}
        </CommandSection>
      </div>

      <div className="command-two-column">
        <OperationsTimeline />
        <ReviewQueuePanel />
      </div>
    </div>
  )
}
