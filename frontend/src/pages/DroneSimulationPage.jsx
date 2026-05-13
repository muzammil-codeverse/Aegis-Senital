import { useMemo, useState } from 'react'
import DroneCameraGrid from '../components/drone/DroneCameraGrid'
import DroneControlPanel from '../components/drone/DroneControlPanel'
import DroneFlightPathPanel from '../components/drone/DroneFlightPathPanel'
import DroneMapOverlayPanel from '../components/drone/DroneMapOverlayPanel'
import DroneMissionQuickActions from '../components/drone/DroneMissionQuickActions'
import DroneRuntimeSelector from '../components/drone/DroneRuntimeSelector'
import DroneSafetyBadge from '../components/drone/DroneSafetyBadge'
import DroneStatusPanel from '../components/drone/DroneStatusPanel'
import DroneTelemetryPanel from '../components/drone/DroneTelemetryPanel'
import DroneVideoPreview from '../components/drone/DroneVideoPreview'
import CommandPageHeader from '../components/layout/CommandPageHeader'
import { useDroneSimulation } from '../hooks/useDroneSimulation'

export default function DroneSimulationPage() {
  const drone = useDroneSimulation()
  const [selectedCamera, setSelectedCamera] = useState('front_center')
  const [selectedPreset, setSelectedPreset] = useState('fixed_camera_handoff_demo')

  if (!drone.canRead) {
    return <p className="muted">You do not have drone:read permission.</p>
  }

  const selectedFrame = useMemo(() => {
    return drone.cameraFrames[selectedCamera] || drone.latestFrame
  }, [drone.cameraFrames, drone.latestFrame, selectedCamera])

  return (
    <div className="space-y-4">
      <CommandPageHeader
        eyebrow="Drone Operations"
        title="Drone Simulation"
        description="Live simulated aerial observation workspace backed by the Cosys-AirSim runtime. This page never claims a real drone feed."
        badges={['Simulated aerial observation', 'Operator review required']}
        actions={(
          <button type="button" className="command-action-button" onClick={drone.refreshAll}>
            Refresh status
          </button>
        )}
      />

      <DroneSafetyBadge />

      {drone.error ? (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{drone.error}</div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <DroneRuntimeSelector
          runtimeStatus={drone.runtimeStatus || drone.status?.runtimeStatus}
          onLaunchRuntime={drone.launchRuntime}
          onRefreshStatus={drone.refreshAll}
        />
        <DroneMissionQuickActions
          selectedPreset={selectedPreset}
          onSelectPreset={setSelectedPreset}
          onRunPreset={drone.runMissionDemo}
        />
      </div>

      <section className="panel" style={{ padding: 12 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Multi-Camera</p>
            <h2>Simulated Drone Camera Grid</h2>
          </div>
        </div>
        <DroneCameraGrid
          cameras={drone.cameraSources}
          cameraFrames={drone.cameraFrames}
          selectedCamera={selectedCamera}
          onSelectCamera={setSelectedCamera}
          onRefreshCamera={drone.refreshCameraFrame}
          autoRefresh
        />
      </section>

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
          <DroneVideoPreview frame={selectedFrame} stats={drone.stats} onRefresh={() => drone.refreshCameraFrame(selectedCamera)} />
          <DroneTelemetryPanel telemetry={drone.telemetry} />
          <DroneFlightPathPanel flightPath={drone.flightPath} />
        </div>
      </div>
    </div>
  )
}
