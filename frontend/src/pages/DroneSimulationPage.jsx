import DroneControlPanel from '../components/drone/DroneControlPanel'
import DroneFlightPathPanel from '../components/drone/DroneFlightPathPanel'
import DroneMapOverlayPanel from '../components/drone/DroneMapOverlayPanel'
import DroneSafetyBadge from '../components/drone/DroneSafetyBadge'
import DroneStatusPanel from '../components/drone/DroneStatusPanel'
import DroneTelemetryPanel from '../components/drone/DroneTelemetryPanel'
import DroneVideoPreview from '../components/drone/DroneVideoPreview'
import { useDroneSimulation } from '../hooks/useDroneSimulation'

export default function DroneSimulationPage() {
  const drone = useDroneSimulation()

  if (!drone.canRead) {
    return <p className="muted">You do not have drone:read permission.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded border bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Drone simulation</p>
          <h1 className="text-xl font-semibold text-slate-950">Simulated aerial intelligence source</h1>
        </div>
        <button type="button" className="rounded border px-3 py-2 text-xs text-slate-700" onClick={drone.refreshAll}>
          Refresh status
        </button>
      </div>

      <DroneSafetyBadge />

      {drone.error ? (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{drone.error}</div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[320px,1fr]">
        <div className="space-y-4">
          <DroneStatusPanel status={drone.status} stats={drone.stats} wsStatus={drone.wsStatus} />
          <DroneControlPanel
            canControl={drone.canControl}
            status={drone.status}
            actionError={drone.actionError}
            onStart={drone.startSession}
            onStop={drone.stopSession}
            onTakeoff={drone.takeoff}
            onLand={drone.land}
            onHover={drone.hover}
            onMove={drone.move}
          />
          <DroneMapOverlayPanel telemetry={drone.telemetry} flightPath={drone.flightPath} />
        </div>
        <div className="space-y-4">
          <DroneVideoPreview frame={drone.latestFrame} stats={drone.stats} onRefresh={drone.refreshFrame} />
          <DroneTelemetryPanel telemetry={drone.telemetry} />
          <DroneFlightPathPanel flightPath={drone.flightPath} />
        </div>
      </div>
    </div>
  )
}
