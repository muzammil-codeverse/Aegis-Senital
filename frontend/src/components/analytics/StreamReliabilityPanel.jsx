import { formatNumber } from '../../utils/formatters'
import EmptyState from '../common/EmptyState'

export default function StreamReliabilityPanel({ streamReliability = [] }) {
  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Stream Reliability</p>
          <h2>Decode and Delivery Health</h2>
        </div>
        <span className="count-pill">{streamReliability.length} streams</span>
      </div>
      {streamReliability.length === 0 ? <EmptyState message="No active stream telemetry is available." /> : (
        <div className="analytics-inline-list">
          {streamReliability.map(stream => (
            <article key={stream.camera_id} className="analytics-inline-card analytics-inline-card-wide">
              <div className="analytics-inline-head">
                <strong>{stream.camera_id}</strong>
                <span className={`state-chip ${stream.stream_status === 'healthy' ? 'health-normal' : 'health-degraded'}`}>{stream.stream_status}</span>
              </div>
              <div className="analytics-inline-metrics">
                <span>Decoded {formatNumber(stream.fps_decode)} fps</span>
                <span>Processed {formatNumber(stream.fps_processed)} fps</span>
                <span>Dropped {formatNumber(stream.dropped_frames_total)}</span>
                <span>Reconnects {formatNumber(stream.reconnect_attempts)}</span>
                <span>Offline {formatNumber(stream.offline_transitions)}</span>
                <span>Preview {formatNumber(stream.preview_clients)}</span>
              </div>
              <div className="button-row">
                <span className="state-chip">{stream.hls_available ? 'HLS' : 'No HLS'}</span>
                <span className="state-chip">{stream.webrtc_enabled ? 'WebRTC' : 'WebRTC off'}</span>
                <span className="state-chip">{stream.mjpeg_available ? 'MJPEG' : 'MJPEG off'}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
