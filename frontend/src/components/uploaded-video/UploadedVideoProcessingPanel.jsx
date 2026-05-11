export default function UploadedVideoProcessingPanel({
  session,
  status,
  connectionStatus,
  busy = false,
  onStart,
  onCancel,
}) {
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
  const progress = activeStatus.progress || {}
  const percent = Number(progress.percent || 0)

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Session</p>
          <h2>{session.original_filename}</h2>
        </div>
        <div className="button-row">
          <span className="state-chip">Integrity SHA-256</span>
          <span className={`count-pill ${activeStatus.status === 'completed' ? 'status-open' : ''}`}>
            {activeStatus.status || session.status}
          </span>
        </div>
      </div>
      <div className="drawer-grid case-health-grid">
        <span>Session ID</span><strong>{session.session_id}</strong>
        <span>Source</span><strong>{session.source_type}</strong>
        <span>Storage</span><strong>{session.safe_filename}</strong>
        <span>Duration</span><strong>{Number(session.duration_seconds || 0).toFixed(1)}s</strong>
        <span>Frames</span><strong>{session.frame_count || 0}</strong>
        <span>FPS</span><strong>{Number(session.fps || 0).toFixed(2)}</strong>
        <span>Progress WS</span><strong>{connectionStatus}</strong>
        <span>Report</span><strong>{activeStatus.report_ready ? 'Ready' : 'Pending'}</strong>
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
      <div className="button-row">
        <button
          type="button"
          className="primary-button"
          disabled={busy || ['processing', 'queued', 'completed'].includes(activeStatus.status)}
          onClick={() => onStart(session.session_id)}
        >
          Start Processing
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={busy || !['processing', 'queued'].includes(activeStatus.status)}
          onClick={() => onCancel(session.session_id)}
        >
          Cancel
        </button>
        <span className="muted">{session.hash_sha256?.slice(0, 20)}…</span>
      </div>
    </section>
  )
}
