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
import CommandPageHeader from '../components/layout/CommandPageHeader'
import { useDroneMissions } from '../hooks/useDroneMissions'

export default function DroneMissionPlannerPage() {
  const {
    missions,
    loading,
    error,
    cityPresets,
    cityPresetError,
    evidenceBundle,
    activeSession,
    telemetry,
    events,
    report,
    fetchMissions,
    fetchCityPresets,
    handleCreate,
    handleDelete,
    handleImportCityPreset,
    handleStart,
    handlePause,
    handleResume,
    handleCancel,
    loadEvidenceBundle,
  } = useDroneMissions()

  const [selectedMission, setSelectedMission] = useState(null)
  const [newName, setNewName] = useState('Simulated Aerial Patrol Mission')
  const [newRouteType, setNewRouteType] = useState('linear')
  const [newWaypoints, setNewWaypoints] = useState([])
  const [selectedPreset, setSelectedPreset] = useState('fixed_camera_handoff_demo')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [presetLoading, setPresetLoading] = useState(false)
  const [presetError, setPresetError] = useState(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)

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

  async function onImportPreset() {
    setPresetLoading(true)
    setPresetError(null)
    try {
      const mission = await handleImportCityPreset(selectedPreset)
      setSelectedMission(mission)
    } catch (err) {
      setPresetError(err.message)
    } finally {
      setPresetLoading(false)
    }
  }

  async function onExportEvidence() {
    if (!activeSession?.session_id) return
    setEvidenceLoading(true)
    try {
      await loadEvidenceBundle(activeSession.session_id)
    } finally {
      setEvidenceLoading(false)
    }
  }

  const selectedPresetDetails = cityPresets.find(item => item.name === selectedPreset) || null

  return (
    <div className="page-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <CommandPageHeader
        eyebrow="Drone Operations"
        title="Drone Mission Planner"
        description="Plan and monitor simulated aerial patrol missions via Cosys-AirSim. Mission outputs remain simulated and operator-reviewed."
        badges={['Simulated mission workflow', 'Operator review required']}
        actions={<MissionSafetyBadge />}
      />

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
              <div style={{ marginBottom: 10, padding: 8, border: '1px solid #334155', borderRadius: 6 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>City Mission Presets</div>
                <label style={{ fontSize: 11, display: 'block' }}>
                  Preset
                  <select
                    value={selectedPreset}
                    onChange={event => setSelectedPreset(event.target.value)}
                    style={{ display: 'block', width: '100%', marginTop: 2 }}
                  >
                    {(cityPresets || []).map(preset => (
                      <option key={preset.name} value={preset.name}>{preset.name}</option>
                    ))}
                  </select>
                </label>
                <div className="button-row" style={{ marginTop: 6 }}>
                  <button className="btn btn-sm" type="button" onClick={fetchCityPresets}>Refresh presets</button>
                  <button className="btn btn-sm btn-primary" type="button" onClick={onImportPreset} disabled={presetLoading || !cityPresets.length}>
                    {presetLoading ? 'Importing...' : 'Import preset'}
                  </button>
                </div>
                {selectedPresetDetails ? (
                  <div style={{ marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
                    Expected outcome: {selectedPresetDetails.expected_demo_outcome || 'n/a'}
                  </div>
                ) : null}
                {cityPresetError ? <div style={{ marginTop: 6, color: '#f87171', fontSize: 11 }}>{cityPresetError}</div> : null}
                {presetError ? <div style={{ marginTop: 6, color: '#f87171', fontSize: 11 }}>{presetError}</div> : null}
              </div>

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
          {/* Exhibition card: shown when no mission is selected and no missions exist */}
          {!selectedMission && missions.length === 0 && !loading && (
            <div className="panel" style={{ border: '1px solid #1d4ed8', background: '#0f172a' }}>
              <div className="panel-header" style={{ borderBottom: '1px solid #1d4ed8' }}>
                <div>
                  <p className="eyebrow" style={{ color: '#60a5fa' }}>DRONE-ALPHA</p>
                  <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0 }}>Bank Robbery Response Mission — Demo Route</h3>
                </div>
                <span style={{ background: '#1d4ed8', borderRadius: 4, padding: '2px 8px', fontSize: 10, fontWeight: 700, color: '#93c5fd', textTransform: 'uppercase' }}>
                  Synthetic
                </span>
              </div>
              <div className="panel-body" style={{ padding: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12, fontSize: 12 }}>
                  <div><span style={{ color: '#6b7280' }}>Vehicle</span> <strong>DRONE-ALPHA</strong></div>
                  <div><span style={{ color: '#6b7280' }}>Provider</span> <strong>Synthetic / AirSim</strong></div>
                  <div><span style={{ color: '#6b7280' }}>Route type</span> <strong>Linear — Bank to Parking Zone</strong></div>
                  <div><span style={{ color: '#6b7280' }}>Waypoints</span> <strong>5</strong></div>
                  <div><span style={{ color: '#6b7280' }}>Mission status</span> <strong style={{ color: '#f59e0b' }}>Awaiting Import</strong></div>
                  <div><span style={{ color: '#6b7280' }}>AirSim</span> <strong style={{ color: '#6b7280' }}>Offline — Synthetic active</strong></div>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>Demo Waypoints</div>
                  {[
                    { id: 'WP-1', label: 'Bank Entrance (launch point)', lat: 48.8566, lon: 2.3522 },
                    { id: 'WP-2', label: 'Market Street intersection', lat: 48.8570, lon: 2.3530 },
                    { id: 'WP-3', label: 'Road corridor observation', lat: 48.8575, lon: 2.3545 },
                    { id: 'WP-4', label: 'Alley junction sweep', lat: 48.8578, lon: 2.3558 },
                    { id: 'WP-5', label: 'Parking Zone (target intercept)', lat: 48.8582, lon: 2.3570 },
                  ].map((wp, i) => (
                    <div key={wp.id} style={{ display: 'flex', gap: 8, padding: '3px 0', borderBottom: '1px solid #1e293b', fontSize: 12 }}>
                      <span style={{ color: '#60a5fa', fontWeight: 600, width: 40, flexShrink: 0 }}>{wp.id}</span>
                      <span style={{ flex: 1, color: '#d1d5db' }}>{wp.label}</span>
                      <span style={{ color: '#374151', fontSize: 10 }}>{wp.lat.toFixed(4)}, {wp.lon.toFixed(4)}</span>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>
                  Import the bank robbery response preset from the left panel to activate this mission route for real simulation.
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ fontSize: 11 }}
                  onClick={() => {
                    setSelectedPreset('fixed_camera_handoff_demo')
                    onImportPreset()
                  }}
                  disabled={presetLoading || cityPresets.length === 0}
                >
                  {presetLoading ? 'Importing...' : 'Import Bank Robbery Response Mission'}
                </button>
              </div>
            </div>
          )}

          {/* Route visualisation */}
          <div className="panel">
            <div className="panel-header">
              {selectedMission ? selectedMission.name : (missions.length > 0 ? 'Select a mission from the list' : 'No mission selected')}
            </div>
            <div className="panel-body" style={{ padding: 8 }}>
              <MissionPlannerCanvas
                mission={selectedMission}
                session={activeSession}
                telemetry={telemetry}
                selectedPreset={selectedPresetDetails}
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
                  selectedPreset={selectedPresetDetails}
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

          {activeSession && (
            <div className="panel">
              <div className="panel-header">
                <span>Mission Evidence Export</span>
                <button className="btn btn-sm" type="button" onClick={onExportEvidence} disabled={evidenceLoading}>
                  {evidenceLoading ? 'Exporting...' : 'Export bundle'}
                </button>
              </div>
              <div className="panel-body" style={{ padding: 8, fontSize: 12 }}>
                <div className="button-row">
                  <span className="state-chip">simulated_geo=true</span>
                  <span className="state-chip">Operator review required</span>
                </div>
                {selectedPresetDetails ? (
                  <p style={{ marginTop: 8 }}>
                    Safe wording: {selectedPresetDetails.safe_wording || 'Simulated aerial observation.'}
                  </p>
                ) : null}
                {evidenceBundle ? (
                  <p style={{ marginTop: 8, color: '#94a3b8' }}>
                    Export includes telemetry summary, route summary, detection summary, and fusion summary.
                  </p>
                ) : (
                  <p style={{ marginTop: 8, color: '#94a3b8' }}>
                    Export a bundle after or during a mission to attach simulated evidence to a reviewable case.
                  </p>
                )}
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
