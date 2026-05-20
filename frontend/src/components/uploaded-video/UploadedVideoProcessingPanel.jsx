export default function UploadedVideoProcessingPanel({
  session,
  status,
  connectionStatus,
  error,
  busy = false,
  onStart,
  onCancel,
}) {
  const runningStates = new Set(['queued', 'processing', 'frame_extraction', 'inference', 'event_generation', 'report_generation'])
  const terminalStates = new Set(['completed', 'failed', 'cancelled'])
  const statusOrder = [
    'uploaded',
    'queued',
    'processing',
    'frame_extraction',
    'inference',
    'event_generation',
    'report_generation',
    'completed',
  ]
  const statusLabels = {
    created: 'CREATED',
    uploaded: 'UPLOADED',
    queued: 'QUEUED',
    processing: 'PROCESSING',
    frame_extraction: 'FRAME EXTRACTION',
    inference: 'INFERENCE',
    event_generation: 'EVENT GENERATION',
    report_generation: 'REPORT GENERATION',
    completed: 'COMPLETED',
    failed: 'FAILED',
    cancelled: 'CANCELLED',
  }

  if (!session) {
    return (
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Processing</p>
            <h2>Session Status</h2>
          </div>
        </div>
        <p className="muted">Upload a video to initialize a durable analysis session.</p>
      </section>
    )
  }

  const activeStatus = status || { status: session.status, progress: session.progress || {} }
  const statusValue = String(activeStatus.status || session.status || 'unknown').toLowerCase()
  const progress = activeStatus.progress || {}
  const percent = Number(progress.percent || 0)
  const failureReason = activeStatus.last_error || session.metadata?.last_error || null
  const detectorNotReady = failureReason && /detector|model|artifact|capability/i.test(failureReason)
  const currentIndex = statusOrder.indexOf(statusValue)
  const canStart = !busy && !runningStates.has(statusValue) && statusValue !== 'completed'
  const canCancel = !busy && runningStates.has(statusValue)
  const statusClass = statusValue === 'failed' ? 'status-error' : statusValue === 'completed' ? 'status-open' : ''

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Session</p>
          <h2>{session.original_filename}</h2>
        </div>
        <div className="button-row">
          <span className="state-chip">Integrity SHA-256</span>
          <span className={`count-pill ${statusClass}`}>
            {statusLabels[statusValue] || statusValue.toUpperCase()}
          </span>
        </div>
      </div>
      <div className="drawer-grid case-health-grid">
        <span>Session ID</span><strong>{session.session_id}</strong>
        <span>Uploaded</span><strong>{session.created_at ? new Date(session.created_at).toLocaleString([], { hour12: false }) : 'N/A'}</strong>
        <span>Source</span><strong>{session.source_type}</strong>
        <span>Storage</span><strong>{session.safe_filename}</strong>
        <span>Duration</span><strong>{Number(session.duration_seconds || 0).toFixed(1)}s</strong>
        <span>Frames</span><strong>{session.frame_count || 0}</strong>
        <span>FPS</span><strong>{Number(session.fps || 0).toFixed(2)}</strong>
        <span>Progress WS</span><strong>{connectionStatus}</strong>
        <span>Report</span><strong>{activeStatus.report_ready ? 'Ready' : 'Pending'}</strong>
        <span>Events</span><strong>{activeStatus.event_count ?? 0}</strong>
      </div>
      <div className="uploaded-video-progress">
        <div className="uploaded-video-progress-bar">
          <div className="uploaded-video-progress-fill" style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
        </div>
        <div className="button-row">
          <span>{progress.frames_processed || 0} / {progress.total_frames || session.frame_count || 0} frames</span>
          <strong>{percent.toFixed(1)}%</strong>
        </div>
      </div>
      <div className="uploaded-video-status-steps" aria-label="Uploaded video processing timeline">
        {statusOrder.map((item, index) => {
          const complete = statusValue === 'completed' || (currentIndex >= 0 && index < currentIndex)
          const active = item === statusValue || (statusValue === 'processing' && item === 'processing')
          return (
            <span key={item} className={`state-chip ${complete ? 'health-normal' : ''} ${active ? 'health-degraded' : ''}`.trim()}>
              {statusLabels[item]}
            </span>
          )
        })}
        {terminalStates.has(statusValue) && !statusOrder.includes(statusValue) ? (
          <span className={`state-chip ${statusClass}`}>{statusLabels[statusValue]}</span>
        ) : null}
      </div>
      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          disabled={!canStart}
          onClick={() => onStart(session.session_id)}
        >
          Start Processing
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={!canCancel}
          onClick={() => onCancel(session.session_id)}
        >
          Cancel
        </button>
        <span className="muted">{session.hash_sha256?.slice(0, 20)}...</span>
      </div>
      {error ? <p className="error-text">Processing status error: {error}</p> : null}
      {statusValue === 'failed' ? (
        <div className="preflight-alert status-error">
          <strong>Processing failed</strong>
          <p>{failureReason || 'The backend reported a failed processing state without a detailed cause.'}</p>
        </div>
      ) : null}
      {detectorNotReady ? (
        <div className="preflight-alert">
          <strong>Detector capability not ready</strong>
          <p>Run EXHIBITION preflight and verify yolo_weapon_detector / yolo_phone_detector model artifacts before retrying this upload.</p>
        </div>
      ) : null}
      {!['uploaded', ...runningStates, ...terminalStates].includes(statusValue) ? (
        <p className="warning-text">Unknown uploaded-video state: {statusValue}. Results are held until the backend reports a known state.</p>
      ) : null}
    </section>
  )
}
