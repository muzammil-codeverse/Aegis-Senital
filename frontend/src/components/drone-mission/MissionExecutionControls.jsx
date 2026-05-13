/**
 * Start / Pause / Resume / Cancel controls for a simulated patrol mission.
 */
export default function MissionExecutionControls({
  selectedMission,
  activeSession,
  selectedPreset,
  onStart,
  onPause,
  onResume,
  onCancel,
  loading,
}) {
  const status = activeSession?.status
  const canStart = selectedMission && (!status || ['completed', 'cancelled', 'failed'].includes(status))
  const canPause = status === 'executing'
  const canResume = status === 'paused'
  const canCancel = status && !['completed', 'cancelled'].includes(status)

  return (
    <div>
      <div className="mission-execution-controls" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          className="btn btn-primary"
          type="button"
          onClick={onStart}
          disabled={!canStart || loading}
        >
          Start Patrol
        </button>
        <button
          className="btn"
          type="button"
          onClick={onPause}
          disabled={!canPause || loading}
        >
          Pause
        </button>
        <button
          className="btn"
          type="button"
          onClick={onResume}
          disabled={!canResume || loading}
        >
          Resume
        </button>
        <button
          className="btn btn-danger"
          type="button"
          onClick={onCancel}
          disabled={!canCancel || loading}
        >
          Cancel
        </button>
      </div>
      {selectedPreset ? (
        <div style={{ marginTop: 8, fontSize: 11, color: '#93c5fd' }}>
          Preset context: {selectedPreset.name} | runtime {selectedPreset.runtime || 'auto'} | camera {selectedPreset.camera || 'front_center'}.
        </div>
      ) : null}
    </div>
  )
}
