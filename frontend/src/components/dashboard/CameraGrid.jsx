import EmptyState from '../common/EmptyState'
import SeverityBadge from '../common/SeverityBadge'
import { compactList, formatPercent } from '../../utils/formatters'

export default function CameraGrid({ cameras = [] }) {
  return (
    <section className="panel camera-grid-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Camera Operations</p>
          <h2>Camera Grid</h2>
        </div>
        <span className="count-pill">{cameras.length}</span>
      </div>
      {cameras.length === 0 ? (
        <EmptyState message="No cameras referenced by live alerts or incidents yet." />
      ) : (
        <div className="camera-grid">
          {cameras.map(camera => (
            <article key={camera.camera_id} className="camera-card">
              <div className="camera-card-top">
                <strong>{camera.camera_id}</strong>
                <SeverityBadge severity={camera.riskSeverity} compact />
              </div>
              <div className="camera-feed-placeholder">
                <span>Feed pending</span>
                <em>RTSP/WebRTC/HLS slot</em>
              </div>
              <div className="camera-card-meta">
                <span>Status <strong>{camera.status}</strong></span>
                <span>Events <strong>{camera.eventCount}</strong></span>
                <span>Risk <strong>{formatPercent(camera.riskScore)}</strong></span>
                <span>Tracks <strong>{compactList(camera.track_ids)}</strong></span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
