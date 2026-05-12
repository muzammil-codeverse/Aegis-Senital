/**
 * Post-mission summary report panel for a simulated patrol.
 * All reports carry simulated=true and operator_review_required=true.
 */
export default function MissionReportPanel({ report }) {
  if (!report) {
    return <div style={{ color: '#666', fontSize: 12, padding: 8 }}>Report not yet available.</div>
  }

  return (
    <div className="mission-report-panel" style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Simulated Patrol Report</div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        <div><span style={{ color: '#888' }}>Status:</span> {report.mission_status}</div>
        <div><span style={{ color: '#888' }}>Completion:</span> {(report.completion_percent || 0).toFixed(1)}%</div>
        <div><span style={{ color: '#888' }}>Waypoints reached:</span> {report.waypoints_reached}/{report.total_waypoints}</div>
        <div><span style={{ color: '#888' }}>Duration:</span> {report.duration_seconds != null ? `${report.duration_seconds.toFixed(0)}s` : 'N/A'}</div>
        <div><span style={{ color: '#888' }}>Telemetry pts:</span> {report.telemetry_count}</div>
        <div><span style={{ color: '#888' }}>Events:</span> {report.event_count}</div>
      </div>

      <div style={{ marginTop: 8, color: '#aaa', fontStyle: 'italic', fontSize: 11 }}>
        {report.summary}
      </div>

      <div style={{ marginTop: 8, color: '#5a7a5a', fontSize: 10 }}>
        Simulated only — operator review required before any operational use
      </div>
    </div>
  )
}
