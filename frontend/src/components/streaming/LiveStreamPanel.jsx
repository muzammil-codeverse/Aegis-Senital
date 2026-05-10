import { useMemo, useRef, useState } from 'react'
import { API_BASE_URL } from '../../config'
import { getMjpegStreamUrl } from '../../api/streamingApi'
import { useHlsStream } from '../../hooks/useHlsStream'
import { useStreamHealth } from '../../hooks/useStreamHealth'
import { useWebRTCStream } from '../../hooks/useWebRTCStream'
import CameraStreamControls from './CameraStreamControls'
import StreamHealthBadge from './StreamHealthBadge'
import StreamStatsPanel from './StreamStatsPanel'

export default function LiveStreamPanel({ camera }) {
  const cameraId = camera?.camera_id
  const videoRef = useRef(null)
  const [transport, setTransport] = useState('webrtc')
  const { health, stats, error, refresh } = useStreamHealth(cameraId, { enabled: Boolean(cameraId) })
  const webrtc = useWebRTCStream(cameraId, videoRef, { enabled: Boolean(cameraId) && transport === 'webrtc' })
  const hls = useHlsStream(cameraId, videoRef, { enabled: Boolean(cameraId) && (transport === 'hls' || webrtc.mode === 'fallback') })

  const previewMode = useMemo(() => {
    if (transport === 'webrtc' && webrtc.mode === 'webrtc') return 'webrtc'
    if ((transport === 'hls' || webrtc.mode === 'fallback') && hls.mode === 'hls') return 'hls'
    return 'mjpeg'
  }, [hls.mode, transport, webrtc.mode])

  if (!cameraId) return null

  const mjpegUrl = webrtc.fallbackUrl || `${API_BASE_URL}${getMjpegStreamUrl(cameraId)}`
  const transportError = webrtc.error || error

  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="panel-header" style={{ marginBottom: 10 }}>
        <div>
          <p className="eyebrow">Streaming</p>
          <h2 style={{ fontSize: '0.95rem' }}>{camera.name || cameraId}</h2>
        </div>
        <StreamHealthBadge status={health?.status || 'stopped'} />
      </div>

      <div className="button-row" style={{ marginBottom: 10 }}>
        <button type="button" className="text-button" onClick={() => setTransport('webrtc')}>WebRTC</button>
        <button type="button" className="text-button" onClick={() => setTransport('hls')}>HLS</button>
        <button type="button" className="text-button" onClick={() => setTransport('mjpeg')}>MJPEG</button>
      </div>

      <div style={{ background: '#08111f', border: '1px solid #1c2535', borderRadius: 8, overflow: 'hidden', minHeight: 180, marginBottom: 10 }}>
        {previewMode === 'mjpeg' ? (
          <img src={mjpegUrl} alt={`${cameraId} preview`} style={{ width: '100%', height: 240, objectFit: 'cover', display: 'block' }} />
        ) : (
          <video ref={videoRef} muted playsInline autoPlay style={{ width: '100%', height: 240, objectFit: 'cover', display: 'block' }} />
        )}
      </div>

      <div style={{ fontSize: '0.72rem', color: '#8b949e', marginBottom: 10 }}>
        Preview mode: <strong style={{ color: '#e6edf3' }}>{previewMode}</strong>
        {health?.latency_ms != null && <> · latency {health.latency_ms} ms</>}
      </div>
      {transportError && <div style={{ marginBottom: 10, color: '#ff7875', fontSize: '0.72rem' }}>{transportError}</div>}

      <CameraStreamControls cameraId={cameraId} onChanged={refresh} />
      <div style={{ marginTop: 10 }}>
        <StreamStatsPanel stats={stats} />
      </div>
    </section>
  )
}
