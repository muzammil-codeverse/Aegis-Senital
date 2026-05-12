/**
 * Drone Patrol Mission Planner Page (Phase 45).
 *
 * Allows operators to:
 *  - Build simulated patrol routes with waypoints
 *  - Start / pause / resume / cancel simulated aerial patrol missions
 *  - Monitor live telemetry and events from the simulator
 *  - Review post-mission reports
 *
 * All missions are simulated-only. Operator review is required.
 * Safe wording is enforced throughout.
 */
import { useState } from 'react'
import MissionExecutionControls from '../components/drone-mission/MissionExecutionControls'
import MissionEventFeed from '../components/drone-mission/MissionEventFeed'
import MissionPlannerCanvas from '../components/drone-mission/MissionPlannerCanvas'
import MissionReportPanel from '../components/drone-mission/MissionReportPanel'
import MissionRouteList from '../components/drone-mission/MissionRouteList'
import MissionSafetyBadge from '../components/drone-mission/MissionSafetyBadge'
import MissionStatusPanel from '../components/drone-mission/MissionStatusPanel'
import MissionTelemetryTimeline from '../components/drone-mission/MissionTelemetryTimeline'
import WaypointEditor from '../components/drone-mission/WaypointEditor'
import { useDroneMissions } from '../hooks/useDroneMissions'

export default function DroneMissionPlannerPage() {
  const {
    missions,
    loading,
    error,
    activeSession,
    telemetry,
    events,
    report,
    fetchMissions,
    handleCreate,
    handleDelete,
    handleStart,
    handlePause,
    handleResume,
    handleCancel,
  } = useDroneMissions()

  const [selectedMission, setSelectedMission] = useState(null)
  const [newName, setNewName] = useState('Simulated Aerial Patrol Mission')
  const [newRouteType, setNewRouteType] = useState('linear')
  const [newWaypoints, setNewWaypoints] = useState([])
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)

  async function onCreateMission(e) {
    e.preventDefault()
    if (newWaypoints.length < 2) {
      setCreateError('Add at least 2 waypoints to create a mission.')
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const mission = await handleCreate({
        name: newName,
        route_type: newRouteType,
        waypoints: newWaypoints,
      })
      setSelectedMission(mission)
      setNewName('Simulated Aerial Patrol Mission')
      setNewWaypoints([])
    } catch (err) {
      setCreateError(err.message)
    } finally {
      setCreating(false)
    }
  }

  async function onStart() {
    if (!selectedMission) return
    setActionLoading(true)
    try { await handleStart(selectedMission.mission_id) }
    catch (err) { console.error('Start failed:', err.message) }
    finally { setActionLoading(false) }
  }

  async function onPause() {
    setActionLoading(true)
    try { await handlePause() }
    finally { setActionLoading(false) }
  }

  async function onResume() {
    setActionLoading(true)
    try { await handleResume() }
    finally { setActionLoading(false) }
  }

  async function onCancel() {
    setActionLoading(true)
    try { await handleCancel() }
    finally { setActionLoading(false) }
  }

  return (
    <div className="page-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>Drone Patrol Mission Planner</h2>
          <p style={{ margin: '4px 0 0', color: '#888', fontSize: 12 }}>
            Plan and monitor simulated aerial patrol missions via Cosys-AirSim
          </p>
        </div>
        <MissionSafetyBadge />
      </div>

      {error && <div className="alert alert-danger" style={{ fontSize: 12 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
        {/* Left column: mission list + create form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="panel">
            <div className="panel-header">
              <span>Missions</span>
              <button className="btn btn-sm" onClick={fetchMissions} disabled={loading}>Refresh</button>
            </div>
            <div className="panel-body" style={{ padding: 8 }}>
              <MissionRouteList
                missions={missions}
                selectedId={selectedMission?.mission_id}
                onSelect={m => setSelectedMission(m)}
                onDelete={id => handleDelete(id)}
              />
            </div>
          </div>

          {/* Create new mission */}
          <div className="panel">
            <div className="panel-header">New Simulated Mission</div>
            <div className="panel-body" style={{ padding: 8 }}>
              <form onSubmit={onCreateMission}>
                <label style={{ fontSize: 11 }}>
                  Mission name
                  <input
                    type="text"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    style={{ display: 'block', width: '100%', marginTop: 2, marginBottom: 8 }}
                  />
                </label>
                <label style={{ fontSize: 11 }}>
                  Route type
                  <select
                    value={newRouteType}
                    onChange={e => setNewRouteType(e.target.value)}
                    style={{ display: 'block', width: '100%', marginTop: 2, marginBottom: 8 }}
                  >
                    <option value="linear">Linear</option>
                    <option value="loop">Loop</option>
                    <option value="return_to_home">Return to Home</option>
                  </select>
                </label>
                <WaypointEditor waypoints={newWaypoints} onChange={setNewWaypoints} />
                {createError && <div style={{ color: '#e74c3c', fontSize: 11, marginTop: 6 }}>{createError}</div>}
                <button
                  className="btn btn-primary"
                  type="submit"
                  disabled={creating}
                  style={{ marginTop: 10, width: '100%' }}
                >
                  {creating ? 'Creating…' : 'Create Mission'}
                </button>
              </form>
            </div>
          </div>
        </div>

        {/* Right column: canvas, controls, status, telemetry, events, report */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Route visualisation */}
          <div className="panel">
            <div className="panel-header">
              {selectedMission ? selectedMission.name : 'No mission selected'}
            </div>
            <div className="panel-body" style={{ padding: 8 }}>
              <MissionPlannerCanvas
                mission={selectedMission}
                session={activeSession}
                telemetry={telemetry}
              />
            </div>
          </div>

          {/* Execution controls */}
          {selectedMission && (
            <div className="panel">
              <div className="panel-header">Execution Controls</div>
              <div className="panel-body" style={{ padding: 8 }}>
                <MissionExecutionControls
                  selectedMission={selectedMission}
                  activeSession={activeSession}
                  onStart={onStart}
                  onPause={onPause}
                  onResume={onResume}
                  onCancel={onCancel}
                  loading={actionLoading}
                />
              </div>
            </div>
          )}

          {/* Mission status */}
          {activeSession && (
            <div className="panel">
              <div className="panel-header">Mission Status</div>
              <div className="panel-body" style={{ padding: 8 }}>
                <MissionStatusPanel session={activeSession} />
              </div>
            </div>
          )}

          {/* Telemetry timeline */}
          {activeSession && (
            <div className="panel">
              <div className="panel-header">Telemetry Timeline</div>
              <div className="panel-body" style={{ padding: 8 }}>
                <MissionTelemetryTimeline telemetry={telemetry} />
              </div>
            </div>
          )}

          {/* Event feed */}
          {activeSession && (
            <div className="panel">
              <div className="panel-header">Mission Events</div>
              <div className="panel-body" style={{ padding: 8 }}>
                <MissionEventFeed events={events} />
              </div>
            </div>
          )}

          {/* Post-mission report */}
          {report && (
            <div className="panel">
              <div className="panel-header">Mission Report</div>
              <div className="panel-body" style={{ padding: 8 }}>
                <MissionReportPanel report={report} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
