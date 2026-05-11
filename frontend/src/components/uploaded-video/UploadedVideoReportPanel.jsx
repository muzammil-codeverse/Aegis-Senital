export default function UploadedVideoReportPanel({ report }) {
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
            <span>Total Events</span><strong>{report.detections_summary?.total_events || 0}</strong>
            <span>Integrity</span><strong>{report.integrity?.status || 'pending'}</strong>
            <span>Models Used</span><strong>{(report.models_used || []).length}</strong>
          </div>
          <div className="uploaded-video-report-grid">
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
          </div>
        </>
      ) : null}
    </section>
  )
}
