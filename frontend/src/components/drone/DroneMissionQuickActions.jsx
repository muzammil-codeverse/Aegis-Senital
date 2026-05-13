const DEFAULT_PRESETS = [
  'perimeter_patrol',
  'incident_response',
  'crowd_monitoring',
  'traffic_corridor_scan',
  'fixed_camera_handoff_demo',
]

export default function DroneMissionQuickActions({
  presets = DEFAULT_PRESETS,
  selectedPreset = 'fixed_camera_handoff_demo',
  onSelectPreset,
  onRunPreset,
  running = false,
}) {
  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Mission Demo</p>
          <h2>Mission Quick Actions</h2>
        </div>
      </div>
      <label style={{ display: 'block', fontSize: 12 }}>
        City mission preset
        <select
          value={selectedPreset}
          onChange={event => onSelectPreset?.(event.target.value)}
          style={{ display: 'block', width: '100%', marginTop: 4 }}
        >
          {presets.map(preset => (
            <option key={preset} value={preset}>{preset}</option>
          ))}
        </select>
      </label>
      <div className="button-row" style={{ marginTop: 10 }}>
        <button type="button" className="text-button" onClick={() => onRunPreset?.(selectedPreset)} disabled={running}>
          Start mission demo
        </button>
        <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-mission-planner' }}>
          Open planner
        </button>
        <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-fusion' }}>
          Open fusion
        </button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        Candidate mission outcomes only. No identity or guilt confirmation.
      </p>
    </section>
  )
}
