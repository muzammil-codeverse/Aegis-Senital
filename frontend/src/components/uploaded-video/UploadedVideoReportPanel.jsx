export default function UploadedVideoReportPanel({ report }) {
  const summary = report?.detections_summary || {}
  const eventTypes = summary.event_types || {}
  const eventEntries = Object.entries(eventTypes)
  const detectedClasses = Array.isArray(summary.detected_classes) ? summary.detected_classes : eventEntries.map(([key]) => key)
  const confidence = summary.confidence_summary || {}
  const totalEvents = Number(summary.total_events || summary.detection_count || 0)
  const commandCenter = report?.metadata?.command_center || {}
  const alertIds = Array.isArray(commandCenter.alert_ids) ? commandCenter.alert_ids : []
  const incidentIds = Array.isArray(commandCenter.incident_ids) ? commandCenter.incident_ids : []
  const evidenceRefs = Array.isArray(commandCenter.evidence_refs) ? commandCenter.evidence_refs : []

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Report</p>
          <h2>Analysis Summary</h2>
        </div>
        <span className="count-pill">{report ? 'Ready' : 'Pending'}</span>
      </div>
      {!report ? <p className="muted">The report is generated when processing completes.</p> : null}
      {report ? (
        <>
          <div className="drawer-grid case-health-grid">
            <span>Source</span><strong>{report.video_metadata?.original_filename || 'N/A'}</strong>
            <span>Processed Frames</span><strong>{report.video_metadata?.frames_processed ?? 0}</strong>
            <span>Total Events</span><strong>{totalEvents}</strong>
            <span>Integrity</span><strong>{report.integrity?.status || 'pending'}</strong>
            <span>Models Used</span><strong>{(report.models_used || []).length}</strong>
            <span>Max Confidence</span><strong>{Number(confidence.max || 0).toFixed(2)}</strong>
            <span>Promoted Alerts</span><strong>{alertIds.length}</strong>
            <span>Evidence Refs</span><strong>{evidenceRefs.length}</strong>
          </div>
          {totalEvents === 0 ? <p className="muted">No detections found.</p> : null}
          <div className="uploaded-video-report-grid">
            <article className="timeline-card">
              <strong>Detection Summary</strong>
              <div className="drawer-grid case-health-grid">
                <span>Classes</span><strong>{detectedClasses.length ? detectedClasses.join(', ') : 'None'}</strong>
                <span>Average Confidence</span><strong>{Number(confidence.average || 0).toFixed(2)}</strong>
                <span>Event Classes</span><strong>{eventEntries.length}</strong>
              </div>
              {eventEntries.length > 0 ? (
                <ul className="uploaded-video-inline-list">
                  {eventEntries.map(([name, count]) => <li key={name}>{name}: {count}</li>)}
                </ul>
              ) : null}
            </article>
            <article className="timeline-card">
              <strong>Model Caveats</strong>
              <ul className="uploaded-video-inline-list">
                {(report.model_caveats || []).map(item => <li key={item}>{item}</li>)}
              </ul>
            </article>
            <article className="timeline-card">
              <strong>Chain of Custody</strong>
              <pre>{JSON.stringify(report.chain_of_custody || {}, null, 2)}</pre>
            </article>
            <article className="timeline-card">
              <strong>Command-Center Linkage</strong>
              {commandCenter.status ? (
                <>
                  <div className="drawer-grid case-health-grid">
                    <span>Status</span><strong>{commandCenter.status}</strong>
                    <span>Alerts</span><strong>{alertIds.length}</strong>
                    <span>Incidents</span><strong>{incidentIds.length}</strong>
                    <span>Evidence</span><strong>{evidenceRefs.length}</strong>
                  </div>
                  <div className="button-row">
                    <button type="button" className="text-button" onClick={() => { window.location.hash = 'alerts' }}>
                      Open Alerts
                    </button>
                    <button type="button" className="text-button" onClick={() => { window.location.hash = 'dashboard' }}>
                      Open Dashboard
                    </button>
                  </div>
                  {alertIds.length > 0 ? (
                    <ul className="uploaded-video-inline-list">
                      {alertIds.slice(0, 5).map(alertId => <li key={alertId}>{alertId}</li>)}
                    </ul>
                  ) : (
                    <p className="muted">No threat alerts were promoted from this report.</p>
                  )}
                </>
              ) : (
                <p className="muted">Command-center promotion has not linked this report yet.</p>
              )}
            </article>
            <article className="timeline-card">
              <strong>Replay clips</strong>
              <p className="muted">
                Possible incident context — operator review required. Clips include SHA-256 metadata when generated.
              </p>
              <div className="drawer-grid case-health-grid">
                <span>Clips generated</span>
                <strong>{report.replay_summary?.clips_generated ?? 0}</strong>
                <span>Events with clip</span>
                <strong>{report.replay_summary?.events_with_clips ?? 0}</strong>
                <span>Events without clip</span>
                <strong>{report.replay_summary?.events_without_clips ?? 0}</strong>
              </div>
              <ul className="uploaded-video-inline-list">
                {(report.replay_clips || []).map(clip => (
                  <li key={clip.clip_id}>
                    <code>{clip.clip_id}</code> — {clip.hash_sha256?.slice(0, 12)}… ({Number(clip.duration_seconds || 0).toFixed(1)}s)
                  </li>
                ))}
              </ul>
            </article>
          </div>
        </>
      ) : null}
    </section>
  )
}
