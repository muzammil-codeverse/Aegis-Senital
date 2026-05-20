import { useState, useEffect, useCallback, useRef } from 'react'
import {
  getVisualSyncStatus,
  setupVisualScene,
  startVisualDemo,
  stopVisualDemo,
  syncVisualToOffset,
  flushVisualScene,
  captureAllSnapshots,
  captureCameraSnapshot,
  listVisualCameras,
  getRealActorMode,
  snapshotImageUrl,
} from '../../api/visualScenarioApi'

// ─── Constants ──────────────────────────────────────────────────────────────

const REAL_ACTOR_MODE_LABEL = {
  real_mesh: 'Real Mesh Actors',
  spawned_mesh: 'Spawned Mesh Proxies',
  proxy_overlay: 'Proxy Overlay',
  unavailable: 'Simulator Offline',
}

const REAL_ACTOR_MODE_COLOR = {
  real_mesh: '#52c41a',
  spawned_mesh: '#1890ff',
  proxy_overlay: '#fa8c16',
  unavailable: '#8c8c8c',
}

const REAL_ACTOR_MODE_DETAIL = {
  real_mesh: 'Character meshes baked into simulator binary are being driven by the scenario.',
  spawned_mesh: 'Vehicle or prop meshes are spawned in the world; human actors render as humanoid proxies.',
  proxy_overlay: 'Visual proxy overlay active — not full animated mesh mode.',
  unavailable: 'AirSim is not running. Visual overlays disabled until the simulator is started.',
}

const POLL_INTERVAL_MS = 5000

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatRelativeTime(iso) {
  if (!iso) return '—'
  try {
    const ts = new Date(iso).getTime()
    if (!Number.isFinite(ts)) return iso
    const deltaSec = Math.max(0, Math.round((Date.now() - ts) / 1000))
    if (deltaSec < 60) return `${deltaSec}s ago`
    if (deltaSec < 3600) return `${Math.floor(deltaSec / 60)}m ago`
    return `${Math.floor(deltaSec / 3600)}h ago`
  } catch {
    return iso
  }
}

// ─── Subcomponents ──────────────────────────────────────────────────────────

function ModeBadge({ mode }) {
  const color = REAL_ACTOR_MODE_COLOR[mode] || '#8c8c8c'
  const label = REAL_ACTOR_MODE_LABEL[mode] || mode || 'unknown'
  return (
    <span
      data-testid="visual-real-actor-mode"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '2px 8px', borderRadius: 4,
        background: `${color}22`,
        border: `1px solid ${color}66`,
        color,
        fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label}
    </span>
  )
}

function ConnectionDot({ connected }) {
  const color = connected ? '#52c41a' : '#ff4d4f'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block' }} />
      <span style={{ fontSize: 11, color, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 700 }}>
        AirSim {connected ? 'Connected' : 'Offline'}
      </span>
    </span>
  )
}

function ActionButton({ label, onClick, disabled, busy, tone = 'default', testId }) {
  const tones = {
    default: '#374151',
    primary: '#1890ff',
    danger: '#ff4d4f',
    success: '#52c41a',
    warning: '#fa8c16',
  }
  const bg = tones[tone] || tones.default
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled || busy}
      style={{
        padding: '6px 12px', borderRadius: 4,
        border: 'none', background: `${bg}22`,
        color: bg, fontWeight: 700, fontSize: 11,
        letterSpacing: '0.04em', textTransform: 'uppercase',
        cursor: disabled || busy ? 'not-allowed' : 'pointer',
        opacity: disabled || busy ? 0.5 : 1,
      }}
    >
      {busy ? '…' : label}
    </button>
  )
}

function CameraSnapshotCard({ camera, onCapture, busy, cacheBust }) {
  const hasSnapshot = Boolean(camera.snapshot_url || camera.snapshot_path)
  const imgSrc = hasSnapshot ? snapshotImageUrl(camera.camera_id, cacheBust) : null
  return (
    <article
      data-testid={`visual-camera-card-${camera.camera_id}`}
      style={{
        background: '#0f172a', border: '1px solid #1f2937',
        borderRadius: 6, padding: 8, minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <strong style={{ fontSize: 12, color: '#e5e7eb' }}>{camera.camera_id}</strong>
        <span style={{ fontSize: 10, color: '#6b7280' }}>{camera.zone_id || '—'}</span>
      </div>
      <div
        style={{
          height: 90, borderRadius: 4, overflow: 'hidden',
          background: hasSnapshot ? '#000' : '#111827',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginBottom: 6,
        }}
      >
        {imgSrc ? (
          <img
            src={imgSrc}
            alt={`${camera.camera_id} snapshot`}
            data-testid={`visual-camera-img-${camera.camera_id}`}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <span style={{ fontSize: 10, color: '#6b7280' }}>No snapshot</span>
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 10, color: '#9ca3af' }}>
        <span title={camera.last_capture_at || ''}>
          {camera.last_capture_at ? formatRelativeTime(camera.last_capture_at) : 'never'}
        </span>
        <button
          type="button"
          data-testid={`visual-camera-capture-${camera.camera_id}`}
          onClick={() => onCapture && onCapture(camera.camera_id)}
          disabled={busy}
          style={{
            padding: '2px 8px', borderRadius: 3,
            background: '#1890ff22', color: '#1890ff',
            border: 'none', fontWeight: 700, fontSize: 10,
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.5 : 1,
          }}
        >
          CAPTURE
        </button>
      </div>
    </article>
  )
}

// ─── Main panel ─────────────────────────────────────────────────────────────

export default function VisualScenarioPanel({
  scenarioRunId = null,
  onStatusChange = null,
  pollIntervalMs = POLL_INTERVAL_MS,
}) {
  const [syncStatus, setSyncStatus] = useState(null)
  const [cameras, setCameras] = useState([])
  const [busyAction, setBusyAction] = useState(null)
  const [busyCamera, setBusyCamera] = useState(null)
  const [error, setError] = useState(null)
  const [cacheBust, setCacheBust] = useState(0)
  const pollRef = useRef(null)

  // ─── Pollers ──────────────────────────────────────────────────────────────

  const refreshStatus = useCallback(async () => {
    try {
      const [status, cams] = await Promise.all([
        getVisualSyncStatus(),
        listVisualCameras(),
      ])
      setSyncStatus(status)
      setCameras(Array.isArray(cams) ? cams : [])
      if (onStatusChange) onStatusChange(status)
      setError(null)
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load visual status')
    }
  }, [onStatusChange])

  useEffect(() => {
    let mounted = true
    const load = async () => {
      if (mounted) await refreshStatus()
    }
    load()
    if (pollIntervalMs > 0) {
      pollRef.current = setInterval(() => { load() }, pollIntervalMs)
    }
    return () => {
      mounted = false
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [refreshStatus, pollIntervalMs])

  // ─── Action handlers ──────────────────────────────────────────────────────

  const runAction = useCallback(async (name, fn) => {
    setBusyAction(name)
    setError(null)
    try {
      const result = await fn()
      setCacheBust(Date.now())
      await refreshStatus()
      return result
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || `${name} failed`)
      throw err
    } finally {
      setBusyAction(null)
    }
  }, [refreshStatus])

  const handleSetup = useCallback(
    () => runAction('setup', () => setupVisualScene()),
    [runAction],
  )

  const handleStartDemo = useCallback(
    () => runAction('start', () => startVisualDemo({ scenario_run_id: scenarioRunId, duration_seconds: 65 })),
    [runAction, scenarioRunId],
  )

  const handleStopDemo = useCallback(
    () => runAction('stop', () => stopVisualDemo({ flush_markers: false })),
    [runAction],
  )

  const handleSyncCurrent = useCallback(
    async () => {
      const offset = syncStatus?.last_t_offset_seconds ?? 0
      return runAction('sync', () => syncVisualToOffset({ t_offset_seconds: offset, capture_snapshot: false }))
    },
    [runAction, syncStatus],
  )

  const handleCaptureAll = useCallback(
    () => runAction('capture-all', () => captureAllSnapshots()),
    [runAction],
  )

  const handleFlush = useCallback(
    () => runAction('flush', () => flushVisualScene()),
    [runAction],
  )

  const handleRefreshMode = useCallback(
    () => runAction('mode-refresh', () => getRealActorMode()),
    [runAction],
  )

  const handleCaptureCamera = useCallback(async (cameraId) => {
    setBusyCamera(cameraId)
    setError(null)
    try {
      await captureCameraSnapshot(cameraId)
      setCacheBust(Date.now())
      await refreshStatus()
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || `Snapshot for ${cameraId} failed`)
    } finally {
      setBusyCamera(null)
    }
  }, [refreshStatus])

  // ─── Derived state ────────────────────────────────────────────────────────

  const connected = Boolean(syncStatus?.connected)
  const realActorMode = syncStatus?.real_actor_mode || syncStatus?.controller?.real_actor_mode || 'unavailable'
  const animationRunning = Boolean(syncStatus?.controller?.animation_running)
  const staticDrawn = Boolean(syncStatus?.controller?.static_drawn)
  const lastSyncOffset = syncStatus?.last_t_offset_seconds
  const lastSyncAt = syncStatus?.last_sync_at
  const spawnedMeshCount = Object.keys(syncStatus?.controller?.spawned_assets || {}).length

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <section
      data-testid="visual-scenario-panel"
      className="panel"
      style={{ padding: 12, borderRadius: 8, background: '#0b1220', border: '1px solid #1f2937' }}
    >
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <p className="eyebrow" style={{ margin: 0, fontSize: 10, letterSpacing: '0.1em', color: '#6b7280', textTransform: 'uppercase' }}>
            Phase XII
          </p>
          <h2 style={{ margin: '2px 0 4px', fontSize: 15, color: '#e5e7eb' }}>Visual Simulation Bridge</h2>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <ConnectionDot connected={connected} />
          <ModeBadge mode={realActorMode} />
        </div>
      </header>

      {/* Fidelity warning */}
      {(realActorMode === 'proxy_overlay' || realActorMode === 'unavailable') && (
        <div
          data-testid="visual-mode-warning"
          style={{
            background: '#1f1300', border: '1px solid #fa8c16',
            borderRadius: 4, padding: 8, marginBottom: 10,
            color: '#fa8c16', fontSize: 11,
          }}
        >
          {REAL_ACTOR_MODE_DETAIL[realActorMode]}
        </div>
      )}

      {error && (
        <div
          data-testid="visual-error"
          style={{
            background: '#2a0f0f', border: '1px solid #ff4d4f',
            borderRadius: 4, padding: 8, marginBottom: 10,
            color: '#ff8888', fontSize: 11,
          }}
        >
          {String(error)}
        </div>
      )}

      {/* Status row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 8, marginBottom: 12,
        }}
      >
        <StatusTile label="Static Scene"     value={staticDrawn ? 'Drawn' : 'Pending'} ok={staticDrawn} />
        <StatusTile label="Animation"        value={animationRunning ? 'Running' : 'Idle'} ok={animationRunning} />
        <StatusTile label="Spawned Meshes"   value={String(spawnedMeshCount)} />
        <StatusTile label="Last Sync Offset" value={lastSyncOffset != null ? `${lastSyncOffset.toFixed(1)}s` : '—'} />
        <StatusTile label="Last Sync"        value={formatRelativeTime(lastSyncAt)} />
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        <ActionButton label="Setup Visual World"    onClick={handleSetup}        busy={busyAction === 'setup'}        tone="primary" testId="visual-action-setup" />
        <ActionButton label="Start Visual Scene"    onClick={handleStartDemo}    busy={busyAction === 'start'}        tone="success" testId="visual-action-start" />
        <ActionButton label="Sync to Current Step"  onClick={handleSyncCurrent}  busy={busyAction === 'sync'}                          testId="visual-action-sync" />
        <ActionButton label="Capture Snapshots"     onClick={handleCaptureAll}   busy={busyAction === 'capture-all'}  tone="primary" testId="visual-action-capture-all" />
        <ActionButton label="Refresh Mode"          onClick={handleRefreshMode}  busy={busyAction === 'mode-refresh'}                  testId="visual-action-refresh-mode" />
        <ActionButton label="Stop Animation"        onClick={handleStopDemo}     busy={busyAction === 'stop'}         tone="warning" testId="visual-action-stop" />
        <ActionButton label="Flush Visual Scene"    onClick={handleFlush}        busy={busyAction === 'flush'}        tone="danger"  testId="visual-action-flush" />
      </div>

      {/* Cameras grid */}
      {cameras.length > 0 && (
        <div>
          <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <p style={{ margin: 0, fontSize: 11, color: '#9ca3af', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Visual Camera Snapshots
            </p>
            <span style={{ fontSize: 10, color: '#6b7280' }}>{cameras.length} cameras</span>
          </header>
          <div
            data-testid="visual-camera-grid"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
              gap: 8,
            }}
          >
            {cameras.map((cam) => (
              <CameraSnapshotCard
                key={cam.camera_id}
                camera={cam}
                onCapture={handleCaptureCamera}
                busy={busyCamera === cam.camera_id}
                cacheBust={cacheBust}
              />
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <footer style={{ marginTop: 10, fontSize: 10, color: '#6b7280', display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <span>
          AirSim host {syncStatus?.controller?.airsim_host}:{syncStatus?.controller?.airsim_port}
        </span>
        <span>
          Snapshots → {syncStatus?.snapshot_dir || '—'}
        </span>
      </footer>
    </section>
  )
}

function StatusTile({ label, value, ok }) {
  const color = ok === undefined ? '#9ca3af' : (ok ? '#52c41a' : '#fa8c16')
  return (
    <div
      style={{
        background: '#111827', border: '1px solid #1f2937',
        borderRadius: 4, padding: 6,
      }}
    >
      <p style={{ margin: 0, fontSize: 9, letterSpacing: '0.08em', color: '#6b7280', textTransform: 'uppercase' }}>{label}</p>
      <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color }}>{value}</p>
    </div>
  )
}
