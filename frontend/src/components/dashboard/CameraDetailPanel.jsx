import { useEffect, useState } from 'react'
import { getCameraStatus, getLatestFrame } from '../../api/camerasApi'
import { normalizeError } from '../../api/client'
import { useStreamControls } from '../../hooks/useStreamControls'
import SeverityBadge from '../common/SeverityBadge'
import LoadingState from '../common/LoadingState'
import { API_BASE_URL } from '../../config'

const STREAM_STATE_COLOR = {
  running: '#52c41a', starting: '#1890ff', paused: '#fa8c16',
  stopped: '#8c8c8c', error: '#ff4d4f', stopping: '#faad14',
}

function Row({ label, value, mono }) {
  if (value == null || value === '') return null
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', borderBottom: '1px solid #111827', fontSize: '0.75rem', gap: 8 }}>
      <span style={{ color: '#6b7280', flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#d1d5db', fontWeight: 500, fontFamily: mono ? 'monospace' : undefined, textAlign: 'right', wordBreak: 'break-all' }}>
        {String(value)}
      </span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <p style={{ margin: '0 0 5px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>{title}</p>
      {children}
    </div>
  )
}

export default function CameraDetailPanel({ camera, onClose, relatedAlerts = [] }) {
  const [statusData, setStatusData] = useState(null)
  const [latestFrame, setLatestFrame] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const streamControls = useStreamControls({ onSuccess: () => load() })

  async function load() {
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

  useEffect(() => { load() }, [camera?.camera_id])

  if (!camera) return null

  const stream = statusData?.stream_session
  const streamState = stream?.state || 'stopped'
  const isBusy = streamControls.busyCameraId === camera.camera_id
  const imageUrl = latestFrame?.image_url ? `${API_BASE_URL}${latestFrame.image_url}` : null
  const mjpegUrl = latestFrame?.mjpeg_url ? `${API_BASE_URL}${latestFrame.mjpeg_url}` : null

  return (
    <aside style={{
      width: 300, background: '#0d1117', border: '1px solid #1c2535',
      borderRadius: 8, display: 'flex', flexDirection: 'column', overflow: 'hidden', flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', borderBottom: '1px solid #1c2535' }}>
        <div>
          <p style={{ margin: 0, fontSize: '0.58rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>Camera Detail</p>
          <h3 style={{ margin: 0, fontSize: '0.85rem', color: '#e6e6e6' }}>{camera.name}</h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <SeverityBadge severity={camera.riskSeverity || 'info'} compact />
          {onClose && (
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: '0.9rem', padding: 0 }}>✕</button>
          )}
        </div>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: '10px 12px' }}>
        {loading && <LoadingState message="Loading…" />}
        {error && <div style={{ color: '#ff7875', fontSize: '0.72rem', marginBottom: 8 }}>{error}</div>}

        <Section title="Identity">
          <Row label="ID"       value={camera.camera_id} mono />
          <Row label="Zone"     value={camera.zone} />
          <Row label="Source"   value={camera.source_type} />
          <Row label="Priority" value={camera.priority} />
          <Row label="Status"   value={camera.status} />
          <Row label="Enabled"  value={camera.enabled ? 'Yes' : 'No'} />
          {camera.metadata?.description && (
            <p style={{ fontSize: '0.7rem', color: '#4b5563', fontStyle: 'italic', margin: '4px 0 0' }}>{camera.metadata.description}</p>
          )}
        </Section>

        <Section title="Stream Session">
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: STREAM_STATE_COLOR[streamState] || '#6b7280', display: 'inline-block' }} />
            <span style={{ fontSize: '0.78rem', color: STREAM_STATE_COLOR[streamState] || '#e6e6e6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 }}>
              {streamState}
            </span>
          </div>
          {stream?.error_reason && <div style={{ fontSize: '0.7rem', color: '#ff7875', marginBottom: 4 }}>{stream.error_reason}</div>}
          <Row label="Stream ID" value={stream?.stream_id} mono />
          <Row label="Started"   value={stream?.started_at ? new Date(stream.started_at * 1000).toLocaleTimeString() : null} />
        </Section>

        <Section title="Latest Frame">
          <Row label="Frame #"    value={latestFrame?.frame_id} />
          <Row label="Detections" value={latestFrame?.detections?.length ?? 0} />
          <Row label="Tracks"     value={latestFrame?.tracks?.length ?? 0} />
          <Row label="Age"        value={latestFrame?.age_seconds != null ? `${latestFrame.age_seconds}s` : null} />
          <Row label="Stale"      value={latestFrame?.stale != null ? (latestFrame.stale ? 'Yes' : 'No') : null} />
          {imageUrl && <Row label="Image"  value={imageUrl} mono />}
          {mjpegUrl && <Row label="MJPEG"  value={mjpegUrl} mono />}
        </Section>

        <Section title="Activity">
          <Row label="Last Frame" value={camera.last_frame_at ? new Date(camera.last_frame_at * 1000).toLocaleTimeString() : 'Never'} />
          <Row label="Last Event" value={camera.last_event_at ? new Date(camera.last_event_at * 1000).toLocaleTimeString() : 'Never'} />
        </Section>

        {latestFrame?.events?.length > 0 && (
          <Section title="Recent Events">
            {latestFrame.events.slice(0, 4).map((ev, i) => (
              <div key={i} style={{ fontSize: '0.7rem', padding: '3px 6px', background: '#0a0f1a', borderRadius: 3, marginBottom: 3 }}>
                <span style={{ color: '#d1d5db' }}>{ev.event_type || ev.type || 'event'}</span>
                {ev.severity && <span style={{ color: '#fa8c16', marginLeft: 6 }}>{ev.severity}</span>}
              </div>
            ))}
          </Section>
        )}

        {latestFrame?.incidents?.length > 0 && (
          <Section title="Recent Incidents">
            {latestFrame.incidents.slice(0, 3).map((inc, i) => (
              <div key={i} style={{ fontSize: '0.7rem', padding: '3px 6px', background: '#0a0f1a', borderRadius: 3, marginBottom: 3 }}>
                <span style={{ color: '#d1d5db' }}>{inc.incident_type || inc.type || 'incident'}</span>
                {inc.severity && <SeverityBadge severity={inc.severity} compact />}
              </div>
            ))}
          </Section>
        )}

        {relatedAlerts.length > 0 && (
          <Section title={`Related Alerts (${relatedAlerts.length})`}>
            {relatedAlerts.slice(0, 5).map(alert => (
              <div key={alert.alert_id} style={{ fontSize: '0.7rem', padding: '3px 6px', background: '#0a0f1a', borderRadius: 3, marginBottom: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#d1d5db', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 160 }}>{alert.title || alert.alert_id}</span>
                <SeverityBadge severity={alert.severity} compact />
              </div>
            ))}
          </Section>
        )}
      </div>

      {/* Controls */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid #1c2535', display: 'flex', gap: 5, flexWrap: 'wrap' }}>
        <button className="ctrl-btn ctrl-btn-start"   disabled={isBusy} onClick={() => streamControls.start(camera.camera_id)} title="Start">▶ Start</button>
        <button className="ctrl-btn ctrl-btn-stop"    disabled={isBusy} onClick={() => streamControls.stop(camera.camera_id)} title="Stop">■ Stop</button>
        <button className="ctrl-btn ctrl-btn-pause"   disabled={isBusy} onClick={() => streamControls.pause(camera.camera_id)} title="Pause">⏸ Pause</button>
        <button className="ctrl-btn ctrl-btn-restart" disabled={isBusy} onClick={() => streamControls.restart(camera.camera_id)} title="Restart">↺</button>
        {streamControls.error && <div style={{ width: '100%', fontSize: '0.68rem', color: '#ff7875', marginTop: 3 }}>{streamControls.error}</div>}
      </div>
    </aside>
  )
}
