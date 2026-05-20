import { useState, useCallback, useEffect, useRef } from 'react'
import { useAuth } from '../../hooks/useAuth'
import {
  getDemoStatus,
  getDemoSnapshot,
  resetDemo,
  startDemo,
  stepDemo,
  autoRunDemo,
  cancelDemo,
  getDemoRunbook,
  getDemoFallback,
} from '../../api/exhibitionDemoApi'
import { syncVisualFromStep } from '../../api/visualScenarioApi'
import VisualScenarioPanel from './VisualScenarioPanel'

// ─── Status badge colours ────────────────────────────────────────────────────

const STATUS_COLOR = {
  not_started: '#6b7280',
  preflight_required: '#faad14',
  ready: '#52c41a',
  running: '#1890ff',
  completed: '#52c41a',
  failed: '#ff4d4f',
  cancelled: '#8c8c8c',
  stale: '#faad14',
}

const STATUS_LABEL = {
  not_started: 'Not Started',
  preflight_required: 'Preflight Required',
  ready: 'Ready',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  stale: 'Stale — Reset Required',
}

function Badge({ value, label, color }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: (color || '#374151') + '22',
      color: color || '#9ca3af',
      border: `1px solid ${color || '#374151'}44`,
      borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700,
      letterSpacing: '0.05em', textTransform: 'uppercase',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color || '#9ca3af', flexShrink: 0 }} />
      {label || value}
    </span>
  )
}

function ProgressBar({ current, total }) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginBottom: 3 }}>
        <span>Progress</span>
        <span>Step {current} / {total} ({pct}%)</span>
      </div>
      <div style={{ background: '#1f2937', borderRadius: 3, height: 6, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: pct === 100 ? '#52c41a' : '#1890ff',
          borderRadius: 3,
          transition: 'width 0.3s ease',
        }} />
      </div>
    </div>
  )
}

function ActionButton({ label, onClick, disabled, variant = 'default', loading, title }) {
  const base = {
    padding: '6px 14px', borderRadius: 4, border: 'none',
    fontSize: 12, fontWeight: 700, cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.4 : 1, letterSpacing: '0.04em', textTransform: 'uppercase',
    transition: 'opacity 0.15s',
  }
  const variants = {
    primary: { background: '#1890ff', color: '#fff' },
    success: { background: '#52c41a', color: '#fff' },
    danger: { background: '#ff4d4f', color: '#fff' },
    warning: { background: '#faad14', color: '#000' },
    default: { background: '#374151', color: '#e5e7eb' },
    fallback: { background: '#7c3aed', color: '#fff' },
  }
  return (
    <button
      style={{ ...base, ...(variants[variant] || variants.default) }}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
    >
      {loading ? '…' : label}
    </button>
  )
}

function errorStatus(error) {
  return error?.status || error?.details?.status || error?.response?.status
}

function errorDetail(error, fallback = 'Action failed') {
  return error?.response?.data?.detail || error?.details?.payload?.detail || error?.message || fallback
}

function RunbookModal({ runbook, onClose }) {
  if (!runbook) return null
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 9999, padding: 24,
    }}>
      <div style={{
        background: '#111827', border: '1px solid #374151', borderRadius: 8,
        width: '100%', maxWidth: 680, maxHeight: '80vh', overflow: 'auto',
        padding: 24, position: 'relative',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 15, color: '#f9fafb' }}>Exhibition Demo Runbook</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        {(runbook.steps || []).map(s => (
          <div key={s.step} style={{ borderLeft: `3px solid ${s.phase === 'critical_event' ? '#ff4d4f' : s.phase === 'drone_response' ? '#1890ff' : '#374151'}`, paddingLeft: 12, marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: '#6b7280', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Step {s.step} — {s.phase}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#f9fafb', marginBottom: 2 }}>{s.title}</div>
            <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>{s.description}</div>
            {s.operator_note && <div style={{ fontSize: 11, color: '#faad14', fontStyle: 'italic' }}>Operator: {s.operator_note}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Main Panel ──────────────────────────────────────────────────────────────

export default function ExhibitionDemoPanel() {
  const auth = useAuth()
  const [session, setSession] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [fallbackData, setFallbackData] = useState(null)
  const [showFallback, setShowFallback] = useState(false)
  const [runbook, setRunbook] = useState(null)
  const [showRunbook, setShowRunbook] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(null)
  const pollingRef = useRef(null)

  const fetchStatus = useCallback(async () => {
    try {
      const status = await getDemoStatus()
      setSession(status)
      setError(null)
    } catch (e) {
      const httpStatus = errorStatus(e)
      if (httpStatus === 401 || httpStatus === 403) {
        setError('Session expired — please log in again.')
      } else if (httpStatus >= 500 || !httpStatus) {
        setError('Demo status unavailable. Backend may be starting.')
      }
    }
  }, [])

  const fetchSnapshot = useCallback(async () => {
    try {
      const snap = await getDemoSnapshot()
      setSnapshot(snap)
    } catch {
      // non-fatal
    }
  }, [])

  // Part A: wait until auth is settled before making API calls
  useEffect(() => {
    if (auth.loading) return
    if (!auth.authenticated) return
    let mounted = true
    const load = async () => {
      await fetchStatus()
      await fetchSnapshot()
      if (mounted) setLoading(false)
    }
    load()
    return () => { mounted = false }
  }, [auth.loading, auth.authenticated, fetchStatus, fetchSnapshot])

  // Poll while demo is running
  useEffect(() => {
    if (session?.status === 'running') {
      pollingRef.current = setInterval(() => {
        fetchStatus()
        fetchSnapshot()
      }, 3000)
    } else {
      clearInterval(pollingRef.current)
    }
    return () => clearInterval(pollingRef.current)
  }, [session?.status, fetchStatus, fetchSnapshot])

  const handleAction = useCallback(async (name, apiFn, args) => {
    setActionLoading(name)
    setError(null)
    try {
      const result = await apiFn(args)
      await Promise.all([fetchStatus(), fetchSnapshot()])
      return result
    } catch (e) {
      const httpStatus = errorStatus(e)
      if (httpStatus === 401 || httpStatus === 403) {
        setError('Session expired — please log in again.')
      } else {
        setError(errorDetail(e))
      }
    } finally {
      setActionLoading(null)
    }
  }, [fetchStatus, fetchSnapshot])

  const pushVisualSync = useCallback(async (stepResult) => {
    if (!stepResult || typeof stepResult !== 'object') return
    try {
      await syncVisualFromStep(stepResult)
    } catch {
      // Visual sync is best-effort; never blocks the demo flow.
    }
  }, [])

  const handleReset = () => handleAction('reset', resetDemo)
  const handleStartStep = () => handleAction('start_step', startDemo, { mode: 'step' })
  const handleStartAuto = () => handleAction('start_auto', startDemo, { mode: 'auto' })
  const handleStep = async () => {
    const result = await handleAction('step', stepDemo)
    await pushVisualSync(result)
    return result
  }
  const handleAutoRun = async () => {
    const result = await handleAction('autorun', autoRunDemo)
    await pushVisualSync(result)
    return result
  }
  const handleCancel = () => handleAction('cancel', cancelDemo)

  const handleRunbook = async () => {
    if (!runbook) {
      try {
        const rb = await getDemoRunbook()
        setRunbook(rb)
      } catch {
        setRunbook({ steps: [], title: 'Runbook unavailable' })
      }
    }
    setShowRunbook(true)
  }

  // Part E: load and display fallback/replay mode
  const handleFallback = async () => {
    setActionLoading('fallback')
    try {
      const fb = await getDemoFallback()
      setFallbackData(fb)
      setShowFallback(true)
    } catch (e) {
      setError('Fallback replay unavailable: ' + (e?.message || 'unknown error'))
    } finally {
      setActionLoading(null)
    }
  }

  const status = session?.status || 'not_started'
  const isRunning = status === 'running'
  const isStale = status === 'stale'
  const canStart = ['not_started', 'ready', 'completed', 'cancelled', 'failed'].includes(status)
  const alertCount = (session?.active_alert_ids || []).length
  const incidentCount = (session?.active_incident_ids || []).length
  const droneAssigned = (session?.assigned_drone_ids || []).includes('DRONE-ALPHA')
  const trackingReady = session?.tracking_ready || false

  const activeEvent = snapshot?.active_event
  const activeCameraId = activeEvent?.camera_id || activeEvent?.source_id || null
  const activeEventTitle = activeEvent?.description || activeEvent?.event_type || null

  // Part A: auth loading state
  if (auth.loading) {
    return (
      <section className="panel" style={{ marginBottom: 8 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Exhibition Mode</p>
            <h2>Bank Robbery Demo</h2>
          </div>
        </div>
        <div style={{ padding: '16px 0', color: '#6b7280', fontSize: 13 }}>Authenticating…</div>
      </section>
    )
  }

  // Part A: not authenticated
  if (!auth.authenticated) {
    return (
      <section className="panel" style={{ marginBottom: 8 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Exhibition Mode</p>
            <h2>Bank Robbery Demo</h2>
          </div>
        </div>
        <div style={{ padding: '16px 0', color: '#faad14', fontSize: 13 }}>
          Session expired — please log in to access the Exhibition Demo.
        </div>
      </section>
    )
  }

  if (loading && !session) {
    return (
      <section className="panel" style={{ marginBottom: 8 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Exhibition Mode</p>
            <h2>Bank Robbery Demo</h2>
          </div>
        </div>
        <div style={{ padding: '16px 0', color: '#6b7280', fontSize: 13 }}>Connecting to demo service…</div>
      </section>
    )
  }

  return (
    <>
      {showRunbook && <RunbookModal runbook={runbook} onClose={() => setShowRunbook(false)} />}

      <section className="panel" style={{ marginBottom: 8, border: '1px solid #1f2937' }}>
        {/* Header */}
        <div className="panel-header" style={{ borderBottom: '1px solid #1f2937', paddingBottom: 10, marginBottom: 12 }}>
          <div>
            <p className="eyebrow">Exhibition Mode</p>
            <h2 style={{ margin: 0 }}>Bank Robbery Demo</h2>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Badge value={status} label={STATUS_LABEL[status] || status} color={STATUS_COLOR[status]} />
            <button onClick={handleRunbook} style={{ background: 'none', border: '1px solid #374151', borderRadius: 4, color: '#9ca3af', fontSize: 11, padding: '3px 8px', cursor: 'pointer' }}>
              Runbook
            </button>
          </div>
        </div>

        {/* Stale state banner — Part I */}
        {isStale && (
          <div style={{ background: '#faad1422', border: '1px solid #faad1444', borderRadius: 4, padding: '8px 12px', marginBottom: 12, fontSize: 12, color: '#faad14' }}>
            <strong>Session Stale:</strong> {session?.last_error || 'Backend was restarted. Click Reset to start fresh.'}
          </div>
        )}

        {/* Fallback replay banner — Part E */}
        {showFallback && fallbackData && (
          <div style={{ background: '#7c3aed22', border: '1px solid #7c3aed44', borderRadius: 4, padding: '10px 12px', marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#a78bfa', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              Demo Replay Mode <span style={{ color: '#6b7280', fontSize: 10, fontWeight: 400 }}>— deterministic fallback, no live run</span>
            </div>
            <div style={{ fontSize: 12, color: '#d1d5db', marginBottom: 6 }}>{fallbackData.fallback_label}</div>
            {fallbackData.timeline_summary && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {fallbackData.timeline_summary.map((ev, i) => (
                  <div key={i} style={{ background: '#1f2937', borderRadius: 3, padding: '4px 8px', fontSize: 11, color: '#9ca3af' }}>
                    <span style={{ color: ev.is_critical ? '#ff4d4f' : '#60a5fa', fontWeight: 700 }}>{ev.event_type}</span>
                    {ev.camera_id ? ` · ${ev.camera_id}` : ''}
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => setShowFallback(false)} style={{ marginTop: 8, background: 'none', border: '1px solid #4b5563', borderRadius: 3, color: '#9ca3af', fontSize: 11, padding: '2px 8px', cursor: 'pointer' }}>
              Hide Replay
            </button>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div style={{ background: '#ff4d4f22', border: '1px solid #ff4d4f44', borderRadius: 4, padding: '8px 12px', marginBottom: 12, fontSize: 12, color: '#ff4d4f' }}>
            {error}
          </div>
        )}

        {/* Progress */}
        {(session?.total_steps > 0) && (
          <div style={{ marginBottom: 14 }}>
            <ProgressBar current={session.current_step} total={session.total_steps} />
          </div>
        )}

        {/* Active Event */}
        {activeEventTitle && (
          <div style={{ background: '#1f2937', borderRadius: 4, padding: '8px 12px', marginBottom: 12, borderLeft: '3px solid #1890ff' }}>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
              Current Event {activeCameraId ? `· ${activeCameraId}` : ''}
            </div>
            <div style={{ fontSize: 13, color: '#f9fafb', fontWeight: 600 }}>{activeEventTitle}</div>
          </div>
        )}

        {/* Status indicators */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 14 }}>
          <div style={{ background: '#111827', borderRadius: 4, padding: '8px 10px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: alertCount > 0 ? '#ff4d4f' : '#374151' }}>{alertCount}</div>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Alerts</div>
          </div>
          <div style={{ background: '#111827', borderRadius: 4, padding: '8px 10px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: incidentCount > 0 ? '#faad14' : '#374151' }}>{incidentCount}</div>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Incidents</div>
          </div>
          <div style={{ background: '#111827', borderRadius: 4, padding: '8px 10px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: droneAssigned ? '#1890ff' : '#374151' }}>
              {droneAssigned ? '▲' : '—'}
            </div>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Drone-α</div>
          </div>
          <div style={{ background: '#111827', borderRadius: 4, padding: '8px 10px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: trackingReady ? '#52c41a' : '#374151' }}>
              {trackingReady ? '●' : '○'}
            </div>
            <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Track</div>
          </div>
        </div>

        {/* Operator guidance */}
        <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 12, minHeight: 18 }}>
          {status === 'not_started' && 'Click Start Demo to begin. Use Step mode for controlled exhibition or Auto-Run for timed demo.'}
          {status === 'ready' && 'System ready. Click Start Demo (Step) or Start Demo (Auto-Run) to begin.'}
          {status === 'stale' && 'Backend was restarted with an active session. Click Reset to start fresh.'}
          {status === 'running' && !droneAssigned && 'Step through the scenario. Weapon detection at Step 4 triggers drone dispatch.'}
          {status === 'running' && droneAssigned && 'DRONE-ALPHA dispatched. Continue stepping to track suspect path and camera handoffs.'}
          {status === 'completed' && 'Scenario complete. Review alerts, incidents, tracking panel, and analytics. Then Reset for next run.'}
          {status === 'cancelled' && 'Demo cancelled. Click Reset to prepare a fresh run.'}
          {status === 'failed' && 'Demo failed. Check error above. Click Reset and try again.'}
          {status === 'preflight_required' && 'Preflight checks failed. Resolve blocking failures before starting demo.'}
        </div>

        {/* Primary actions */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
          {canStart && (
            <>
              <ActionButton
                label="Start Demo (Step)"
                variant="primary"
                onClick={handleStartStep}
                loading={actionLoading === 'start_step'}
                disabled={!!actionLoading}
              />
              <ActionButton
                label="Start Demo (Auto)"
                variant="success"
                onClick={handleStartAuto}
                loading={actionLoading === 'start_auto'}
                disabled={!!actionLoading}
              />
            </>
          )}
          {isRunning && (
            <>
              <ActionButton
                label="Step →"
                variant="primary"
                onClick={handleStep}
                loading={actionLoading === 'step'}
                disabled={!!actionLoading}
              />
              <ActionButton
                label="Auto-Run"
                variant="warning"
                onClick={handleAutoRun}
                loading={actionLoading === 'autorun'}
                disabled={!!actionLoading}
                title="Runs all remaining steps automatically. Only one auto-run at a time."
              />
              <ActionButton
                label="Cancel"
                variant="danger"
                onClick={handleCancel}
                loading={actionLoading === 'cancel'}
                disabled={!!actionLoading}
              />
            </>
          )}
          <ActionButton
            label="Reset"
            variant="default"
            onClick={handleReset}
            loading={actionLoading === 'reset'}
            disabled={!!actionLoading}
          />
          {/* Part E: Fallback Replay button — always available */}
          <ActionButton
            label="Fallback Replay"
            variant="fallback"
            onClick={handleFallback}
            loading={actionLoading === 'fallback'}
            disabled={!!actionLoading}
            title="Show deterministic scenario replay — no live run required"
          />
        </div>

        {/* Navigation links */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <NavLink href="/#operational-tracking" label="View Tracking" disabled={!trackingReady} />
          <NavLink href="/alerts" label="View Alerts" disabled={alertCount === 0} />
          <NavLink href="/incidents" label="View Incidents" disabled={incidentCount === 0} />
          <NavLink href="/analytics" label="Analytics" />
          <NavLink href="/uploaded-video-analysis" label="Uploaded-Video Analysis" />
        </div>

        {/* Report/evidence summary */}
        {snapshot?.report_links && (snapshot.report_links.alert_ids?.length > 0 || snapshot.report_links.incident_ids?.length > 0) && (
          <div style={{ marginTop: 14, background: '#1f2937', borderRadius: 4, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              Scenario Evidence Summary <span style={{ color: '#faad14', fontWeight: 700 }}>SIMULATED</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 12, color: '#d1d5db' }}>
              <span>Scenario: <code style={{ color: '#60a5fa' }}>bank_robbery_demo</code></span>
              <span>Run ID: <code style={{ color: '#60a5fa', fontSize: 10 }}>{session?.scenario_run_id?.slice(0, 14)}…</code></span>
              <span>Alerts: <strong style={{ color: '#ff4d4f' }}>{snapshot.report_links.alert_ids?.length}</strong></span>
              <span>Incidents: <strong style={{ color: '#faad14' }}>{snapshot.report_links.incident_ids?.length}</strong></span>
              <span>Cameras: <strong>{snapshot.report_links.source_cameras?.length}</strong></span>
              <span>Drone: <strong style={{ color: '#1890ff' }}>{snapshot.report_links.drone_assigned}</strong></span>
              <span style={{ gridColumn: '1 / -1', fontSize: 11, color: '#6b7280', fontStyle: 'italic', marginTop: 4 }}>
                {snapshot.report_links.disclaimer}
              </span>
            </div>
          </div>
        )}

        {/* Demo ID */}
        {session?.demo_id && (
          <div style={{ marginTop: 10, fontSize: 10, color: '#374151' }}>
            Demo ID: {session.demo_id}
          </div>
        )}
      </section>

      {/* Phase XII — Visual simulation bridge */}
      <div style={{ marginBottom: 8 }}>
        <VisualScenarioPanel scenarioRunId={session?.scenario_run_id || null} />
      </div>
    </>
  )
}

function NavLink({ href, label, disabled }) {
  if (disabled) {
    return (
      <span style={{
        fontSize: 11, padding: '3px 8px', borderRadius: 3,
        background: '#1f2937', color: '#374151', cursor: 'not-allowed',
        border: '1px solid #374151', textDecoration: 'none',
      }}>
        {label}
      </span>
    )
  }
  return (
    <a href={href} style={{
      fontSize: 11, padding: '3px 8px', borderRadius: 3,
      background: '#1f2937', color: '#60a5fa',
      border: '1px solid #374151', textDecoration: 'none',
    }}>
      {label} ↗
    </a>
  )
}
