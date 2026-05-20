export default function UploadedVideoTimeline({ items = [], sessionId = '', status = '' }) {
  const emptyText = String(status || '').toLowerCase() === 'completed'
    ? 'No event timeline items were generated for this completed session.'
    : 'No timeline items yet. Process the session to populate this view.'

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Timeline</p>
          <h2>Event Sequence</h2>
        </div>
        <span className="count-pill">{items.length} items</span>
      </div>
      {items.length === 0 ? <p className="muted">{emptyText}</p> : null}
      <div className="uploaded-video-timeline">
        {items.map(item => (
          <article key={item.timeline_id || `${item.event_id}-${item.frame_index}`} className="timeline-card">
            <div className="button-row">
              <strong>{item.title}</strong>
              <span className="state-chip">{Number(item.time_offset_seconds || 0).toFixed(1)}s</span>
            </div>
            <p>{item.description || 'Operator review required.'}</p>
            <div className="button-row">
              <span className={`count-pill severity-${item.severity || 'medium'}`}>{item.severity || 'medium'}</span>
              <span className="muted">Frame {item.frame_index ?? 'N/A'}</span>
              {item.replay_clip?.hash_sha256 ? (
                <span className="count-pill status-open" title="Replay clip available">
                  Clip
                </span>
              ) : sessionId ? (
                <span className="muted">No clip</span>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
