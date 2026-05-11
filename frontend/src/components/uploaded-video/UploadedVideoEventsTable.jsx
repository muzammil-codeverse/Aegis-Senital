export default function UploadedVideoEventsTable({ events = [] }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Events</p>
          <h2>Detected Activity</h2>
        </div>
        <span className="count-pill">{events.length} events</span>
      </div>
      {events.length === 0 ? <p className="muted">No persisted uploaded-video events yet.</p> : null}
      {events.length > 0 ? (
        <div className="table-shell">
          <table className="uploaded-video-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Severity</th>
                <th>Offset</th>
                <th>Frame</th>
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
