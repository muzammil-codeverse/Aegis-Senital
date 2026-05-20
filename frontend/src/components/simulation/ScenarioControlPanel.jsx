import LoadingState from '../common/LoadingState'
import ErrorState from '../common/ErrorState'
import EmptyState from '../common/EmptyState'

const STATE_COLOR = {
  idle: '#6b7280',
  running: '#52c41a',
  paused: '#faad14',
  completed: '#1890ff',
  cancelled: '#ff4d4f',
}

const SEVERITY_COLOR = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  medium: '#faad14',
  low: '#52c41a',
  info: '#6b7280',
}

function RunStatusBar({ run }) {
  if (!run) return null
  const progress = run.total_steps > 0 ? Math.round((run.current_step / run.total_steps) * 100) : 0
  const stateColor = STATE_COLOR[run.state] || '#6b7280'
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: '0.72rem', color: '#9ca3af' }}>
        <span style={{ color: stateColor, fontWeight: 600 }}>{run.state.toUpperCase()}</span>
        <span>{run.current_step} / {run.total_steps} steps</span>
      </div>
      <div style={{ height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${progress}%`, background: stateColor, borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: '0.65rem', color: '#6b7280', flexWrap: 'wrap' }}>
        <span>Obs: <strong style={{ color: '#d1d5db' }}>{run.observations_generated}</strong></span>
        <span>Alerts: <strong style={{ color: run.alerts_promoted > 0 ? '#ff4d4f' : '#d1d5db' }}>{run.alerts_promoted}</strong></span>
        <span>Incidents: <strong style={{ color: run.incidents_promoted > 0 ? '#fa8c16' : '#d1d5db' }}>{run.incidents_promoted}</strong></span>
        {run.drone_dispatched && (
          <span style={{ color: '#1890ff' }}>
            Drone: <strong>{run.dispatched_drone_id || 'dispatched'}</strong>
          </span>
        )}
      </div>
    </div>
  )
}

function TimelineEntry({ entry }) {
  const obs = entry.observation || {}
  const severity = obs.severity || 'info'
  const color = SEVERITY_COLOR[severity] || '#6b7280'
  return (
    <li style={{
      display: 'flex', gap: 8, padding: '4px 0',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
    }}>
      <div style={{ flexShrink: 0, width: 24, textAlign: 'right', color: '#4b5563', fontSize: '0.6rem', paddingTop: 2 }}>
        T+{entry.t_offset_seconds}s
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', color, fontWeight: 600 }}>{(entry.event_type || '').replace(/_/g, ' ')}</span>
          {obs.camera_id && <span style={{ fontSize: '0.6rem', color: '#4b5563' }}>{obs.camera_id}</span>}
          {obs.drone_id && <span style={{ fontSize: '0.6rem', color: '#1890ff' }}>{obs.drone_id}</span>}
        </div>
        <div style={{ fontSize: '0.63rem', color: '#6b7280', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {obs.description || entry.event_type}
        </div>
      </div>
      <div style={{ flexShrink: 0, fontSize: '0.6rem', color, alignSelf: 'flex-start', paddingTop: 2 }}>
        {obs.confidence != null ? `${Math.round(obs.confidence * 100)}%` : ''}
      </div>
    </li>
  )
}

export default function ScenarioControlPanel({
  scenarios = [],
  activeRun = null,
  timeline = [],
  loading = false,
  error = null,
  actionLoading = false,
  actionError = null,
  onStart,
  onStep,
  onPause,
  onResume,
  onCancel,
  onReset,
}) {
  const isRunning = activeRun?.state === 'running'
  const isPaused = activeRun?.state === 'paused'
  const isCompleted = activeRun?.state === 'completed' || activeRun?.state === 'cancelled'
  const hasActiveRun = activeRun && !isCompleted
  const bankRobbery = scenarios.find(s => s.scenario_id === 'bank_robbery_demo') || scenarios[0] || null

  return (
    <section className="panel" style={{ marginBottom: 8 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Crime Scenario Engine</p>
          <h2>Scenario Control</h2>
        </div>
        <span className="count-pill">{scenarios.length}</span>
      </div>

      {loading && <LoadingState label="Loading scenarios" />}
      {error && <ErrorState message={error} />}
      {actionError && (
        <div style={{ padding: '4px 0', fontSize: '0.72rem', color: '#ff7875', marginBottom: 6 }}>
          {actionError}
        </div>
      )}

      {!loading && !error && bankRobbery && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: '0.72rem', color: '#9ca3af', marginBottom: 4 }}>
            <strong style={{ color: '#d1d5db' }}>{bankRobbery.name}</strong>
          </div>
          <div style={{ fontSize: '0.65rem', color: '#6b7280', marginBottom: 6 }}>
            {bankRobbery.description}
          </div>
          <div style={{ fontSize: '0.6rem', color: '#4b5563', display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
            <span>{bankRobbery.actors?.length || 0} actors</span>
            <span>{bankRobbery.timeline?.length || 0} timeline events</span>
            <span>{bankRobbery.camera_ids?.length || 0} cameras</span>
            <span>{bankRobbery.drone_ids?.length || 0} drones</span>
          </div>
        </div>
      )}

      <RunStatusBar run={activeRun} />

      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }} onClick={e => e.stopPropagation()}>
        {!hasActiveRun && (
          <>
            <button
              type="button"
              className="ctrl-btn ctrl-btn-start"
              disabled={actionLoading || !bankRobbery}
              onClick={() => onStart && onStart(bankRobbery?.scenario_id, 'step')}
              title="Start in step mode"
            >
              Step Mode
            </button>
            <button
              type="button"
              className="ctrl-btn"
              disabled={actionLoading || !bankRobbery}
              onClick={() => onStart && onStart(bankRobbery?.scenario_id, 'auto')}
              title="Auto-run all steps"
              style={{ background: 'rgba(24,144,255,0.15)', borderColor: 'rgba(24,144,255,0.35)', color: '#1890ff' }}
            >
              Auto Run
            </button>
          </>
        )}

        {isRunning && (
          <button
            type="button"
            className="ctrl-btn ctrl-btn-start"
            disabled={actionLoading}
            onClick={() => onStep && onStep()}
            title="Execute next step"
          >
            Next Step ▶
          </button>
        )}

        {isRunning && (
          <button
            type="button"
            className="ctrl-btn ctrl-btn-pause"
            disabled={actionLoading}
            onClick={() => onPause && onPause()}
          >
            ⏸ Pause
          </button>
        )}

        {isPaused && (
          <button
            type="button"
            className="ctrl-btn ctrl-btn-start"
            disabled={actionLoading}
            onClick={() => onResume && onResume()}
          >
            ▶ Resume
          </button>
        )}

        {hasActiveRun && (
          <button
            type="button"
            className="ctrl-btn ctrl-btn-stop"
            disabled={actionLoading}
            onClick={() => onCancel && onCancel()}
          >
            ■ Cancel
          </button>
        )}

        {(isCompleted || !activeRun) && activeRun && (
          <button
            type="button"
            className="ctrl-btn ctrl-btn-restart"
            disabled={actionLoading}
            onClick={() => onReset && onReset()}
          >
            ↺ Reset
          </button>
        )}
      </div>

      {timeline.length > 0 && (
        <div>
          <div style={{ fontSize: '0.65rem', color: '#6b7280', marginBottom: 4 }}>
            Observation Timeline ({timeline.length} events)
          </div>
          <ol style={{ listStyle: 'none', margin: 0, padding: 0, maxHeight: 200, overflowY: 'auto' }}>
            {timeline.slice().reverse().map((entry, i) => (
              <TimelineEntry key={`${entry.step}-${i}`} entry={entry} index={i} />
            ))}
          </ol>
        </div>
      )}

      {!loading && !activeRun && scenarios.length === 0 && (
        <EmptyState message="No scenarios registered." />
      )}
    </section>
  )
}
