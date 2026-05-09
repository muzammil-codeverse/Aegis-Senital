import { useEffect, useState } from 'react'
import { getCameraStatus, getLatestFrame } from '../../api/camerasApi'
import { normalizeError } from '../../api/client'
import { useStreamControls } from '../../hooks/useStreamControls'
import SeverityBadge from '../common/SeverityBadge'
import LoadingState from '../common/LoadingState'

const STREAM_STATE_COLOR = {
  running: '#52c41a',
  starting: '#1890ff',
  paused: '#fa8c16',
  stopped: '#8c8c8c',
  error: '#ff4d4f',
  stopping: '#faad14',
}

function MetaRow({ label, value }) {
  if (value == null || value === '') return null
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #1f2937', fontSize: '0.78rem' }}>
      <span style={{ color: '#6b7280' }}>{label}</span>
      <span style={{ color: '#e6e6e6', fontWeight: 500 }}>{value}</span>
    </div>
  )
}

export default function CameraDetailPanel({ camera, onClose, relatedAlerts = [] }) {
  const [statusData, setStatusData] = useState(null)
  const [latestFrame, setLatestFrame] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const streamControls = useStreamControls({
    onSuccess: () => loadStatus(),
  })

  async function loadStatus() {
    if (!camera) return
    setLoading(true)
    try {
      const [statusRes, frameRes] = await Promise.all([
        getCameraStatus(camera.camera_id),
        getLatestFrame(camera.camera_id),
      ])
      setStatusData(statusRes.item)
      setLatestFrame(frameRes.item)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
  }, [camera?.camera_id])

  if (!camera) return null

  const stream = statusData?.stream_session
  const streamState = stream?.state || 'stopped'
  const isBusy = streamControls.busyCameraId === camera.camera_id

  return (
    <aside style={{
      width: 320,
      background: '#0d1117',
      border: '1px solid #1f2937',
      borderRadius: 8,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid #1f2937' }}>
        <div>
          <p style={{ margin: 0, fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>Camera Detail</p>
          <h3 style={{ margin: 0, fontSize: '0.9rem', color: '#e6e6e6' }}>{camera.name}</h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <SeverityBadge severity={camera.riskSeverity || 'info'} compact />
          {onClose && (
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: '1rem', padding: '0 2px' }}>✕</button>
          )}
        </div>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: '10px 14px' }}>
        {loading && <LoadingState message="Loading camera detail…" />}
        {error && <div style={{ color: '#ff7875', fontSize: '0.75rem', marginBottom: 8 }}>{error}</div>}

        {/* Camera metadata */}
        <section style={{ marginBottom: 14 }}>
          <p style={{ margin: '0 0 6px', fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>Identity</p>
          <MetaRow label="Camera ID" value={camera.camera_id} />
          <MetaRow label="Zone" value={camera.zone} />
          <MetaRow label="Source" value={camera.source_type} />
          <MetaRow label="Source URI" value={camera.source_uri} />
          <MetaRow label="Priority" value={camera.priority} />
          <MetaRow label="Status" value={camera.status} />
          <MetaRow label="Enabled" value={camera.enabled ? 'Yes' : 'No'} />
          {camera.metadata?.description && (
            <div style={{ fontSize: '0.72rem', color: '#6b7280', marginTop: 6, fontStyle: 'italic' }}>
              {camera.metadata.description}
            </div>
          )}
        </section>

        {/* Stream session state */}
        <section style={{ marginBottom: 14 }}>
          <p style={{ margin: '0 0 6px', fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>Stream Session</p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
              background: STREAM_STATE_COLOR[streamState] || '#8c8c8c',
            }} />
            <span style={{ fontSize: '0.8rem', color: STREAM_STATE_COLOR[streamState] || '#e6e6e6', textTransform: 'uppercase', letterSpacing: 1 }}>
              {streamState}
            </span>
          </div>
          {stream?.error_reason && (
            <div style={{ fontSize: '0.72rem', color: '#ff7875', marginBottom: 6 }}>
              {stream.error_reason}
            </div>
          )}
          {stream?.stream_id && <MetaRow label="Stream ID" value={stream.stream_id} />}
          {stream?.started_at && (
            <MetaRow label="Started" value={new Date(stream.started_at * 1000).toLocaleTimeString()} />
          )}
        </section>

        {/* Latest frame */}
        {latestFrame && latestFrame.status === 'ok' && (
          <section style={{ marginBottom: 14 }}>
            <p style={{ margin: '0 0 6px', fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>Latest Frame</p>
            <MetaRow label="Frame ID" value={latestFrame.frame_id} />
            <MetaRow label="Detections" value={latestFrame.detections?.length ?? 0} />
            <MetaRow label="Updated" value={latestFrame.timestamp ? new Date(latestFrame.timestamp * 1000).toLocaleTimeString() : null} />
          </section>
        )}

        {/* Timestamps */}
        <section style={{ marginBottom: 14 }}>
          <p style={{ margin: '0 0 6px', fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>Activity</p>
          <MetaRow label="Last Frame" value={camera.last_frame_at ? new Date(camera.last_frame_at * 1000).toLocaleTimeString() : 'Never'} />
          <MetaRow label="Last Event" value={camera.last_event_at ? new Date(camera.last_event_at * 1000).toLocaleTimeString() : 'Never'} />
        </section>

        {/* Related alerts */}
        {relatedAlerts.length > 0 && (
          <section style={{ marginBottom: 14 }}>
            <p style={{ margin: '0 0 6px', fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: 1 }}>
              Related Alerts ({relatedAlerts.length})
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {relatedAlerts.slice(0, 5).map(alert => (
                <div key={alert.alert_id} style={{ fontSize: '0.72rem', padding: '4px 6px', background: '#111827', borderRadius: 4, display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#e6e6e6' }}>{alert.title || alert.alert_id}</span>
                  <SeverityBadge severity={alert.severity} compact />
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Stream controls */}
      <div style={{ padding: '10px 14px', borderTop: '1px solid #1f2937', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button className="ctrl-btn ctrl-btn-start" disabled={isBusy} onClick={() => streamControls.start(camera.camera_id)}>Start</button>
        <button className="ctrl-btn ctrl-btn-stop" disabled={isBusy} onClick={() => streamControls.stop(camera.camera_id)}>Stop</button>
        <button className="ctrl-btn ctrl-btn-pause" disabled={isBusy} onClick={() => streamControls.pause(camera.camera_id)}>Pause</button>
        <button className="ctrl-btn ctrl-btn-restart" disabled={isBusy} onClick={() => streamControls.restart(camera.camera_id)}>Restart</button>
        {streamControls.error && (
          <div style={{ width: '100%', fontSize: '0.7rem', color: '#ff7875', marginTop: 4 }}>{streamControls.error}</div>
        )}
      </div>
    </aside>
  )
}
