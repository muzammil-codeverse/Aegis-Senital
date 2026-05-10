import { formatDistanceToNowStrict } from 'date-fns'
import EmptyState from '../common/EmptyState'

function cellStyle(score) {
  const opacity = Math.min(0.95, Math.max(0.14, Number(score || 0) / 100))
  return { background: `rgba(255, 92, 108, ${opacity})` }
}

export default function CameraRiskHeatmap({ cameraRisk = [], cameraHeatmap = [] }) {
  const rows = (cameraHeatmap.length ? cameraHeatmap : cameraRisk).slice(0, 12)

  return (
    <section className="panel analytics-panel analytics-span-7">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Camera Risk</p>
          <h2>Heatmap and Priority Queue</h2>
        </div>
        <span className="count-pill">{rows.length} cameras</span>
      </div>
      {rows.length === 0 ? <EmptyState message="No camera risk has been computed for the selected window." /> : (
        <>
          <div className="analytics-heatmap-grid">
            {rows.map(item => (
              <article key={item.camera_id} className="analytics-heatmap-cell" style={cellStyle(item.risk_score)}>
                <strong>{item.camera_id}</strong>
                <span>{item.review_priority} priority</span>
                <em>{item.risk_score.toFixed(1)}</em>
              </article>
            ))}
          </div>
          <div className="table-scroll">
            <table className="security-table analytics-table">
              <thead>
                <tr>
                  <th>Camera</th>
                  <th>Risk Score</th>
                  <th>Critical Events</th>
                  <th>Open Cases</th>
                  <th>Stream</th>
                  <th>Last Event</th>
                </tr>
              </thead>
              <tbody>
                {cameraRisk.slice(0, 8).map(item => (
                  <tr key={item.camera_id}>
                    <td>{item.camera_id}</td>
                    <td>{item.risk_score.toFixed(1)}</td>
                    <td>{item.critical_event_count}</td>
                    <td>{item.open_case_count}</td>
                    <td>{item.stream_status}</td>
                    <td>{item.last_event_time ? formatDistanceToNowStrict(new Date(item.last_event_time), { addSuffix: true }) : 'No recent event'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
