import UploadedVideoClipControls from './UploadedVideoClipControls'

export default function UploadedVideoEventsTable({ events = [], sessionId = '', status = '' }) {
  const terminalStatus = String(status || '').toLowerCase()
  const emptyText = terminalStatus === 'completed'
    ? 'No detections found.'
    : 'No persisted uploaded-video events yet.'

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Events</p>
          <h2>Detected Activity</h2>
        </div>
        <span className="count-pill">{events.length} events</span>
      </div>
      {events.length === 0 ? <p className="muted">{emptyText}</p> : null}
      {events.length > 0 ? (
        <div className="table-shell">
          <table className="uploaded-video-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Severity</th>
                <th>Offset</th>
                <th>Frame</th>
                <th>Clip</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {events.map(event => (
                <tr key={event.event_id}>
                  <td>{event.event_type}</td>
                  <td><span className={`count-pill severity-${event.severity || 'medium'}`}>{event.severity || 'medium'}</span></td>
                  <td>{Number(event.time_offset_seconds || 0).toFixed(1)}s</td>
                  <td>{event.frame_index ?? 'N/A'}</td>
                  <td>
                    {event.replay_clip?.hash_sha256 ? (
                      <span className="count-pill status-open">Available</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                    {sessionId ? (
                      <UploadedVideoClipControls sessionId={sessionId} eventId={event.event_id} replayClip={event.replay_clip} />
                    ) : null}
                  </td>
                  <td>{event.summary || 'Operator review required.'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
