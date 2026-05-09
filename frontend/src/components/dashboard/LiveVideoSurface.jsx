import { useEffect, useRef, useState } from 'react'
import SeverityBadge from '../common/SeverityBadge'
import { API_BASE_URL } from '../../config'

const DISPLAY_STATES = {
  LIVE:           { label: 'LIVE',        color: '#52c41a', pulse: true },
  LIVE_ANNOTATED: { label: 'LIVE ANN',    color: '#52c41a', pulse: true },
  SNAPSHOT:       { label: 'SNAPSHOT',    color: '#1890ff', pulse: false },
  ANNOTATED:      { label: 'ANNOTATED',   color: '#1890ff', pulse: false },
  REPLAY_FRAME:   { label: 'REPLAY',      color: '#9b59b6', pulse: false },
  STALE:          { label: 'STALE',       color: '#fa8c16', pulse: false },
  OFFLINE:        { label: 'OFFLINE',     color: '#ff7875', pulse: false },
  ERROR:          { label: 'ERROR',       color: '#ff4d4f', pulse: false },
  NO_FRAME:       { label: 'NO FRAME',    color: '#6b7280', pulse: false },
  DISABLED:       { label: 'DISABLED',    color: '#595959', pulse: false },
  PLACEHOLDER:    { label: 'PLACEHOLDER', color: '#374151', pulse: false },
}

function StatusBanner({ state }) {
  const cfg = DISPLAY_STATES[state] || DISPLAY_STATES.NO_FRAME
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 8px', borderRadius: 3,
      border: `1px solid ${cfg.color}`,
      background: `${cfg.color}18`,
    }}>
      {cfg.pulse && (
        <span style={{
          display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
          background: cfg.color, animation: 'aegisPulse 1.2s ease-in-out infinite',
        }} />
      )}
      <span style={{ fontSize: '0.6rem', fontWeight: 700, color: cfg.color, letterSpacing: 1 }}>
        {cfg.label}
      </span>
    </div>
  )
}

function OverlayBox({ item, scaleX, scaleY }) {
  const bbox = item.bbox
  if (!Array.isArray(bbox) || bbox.length < 4) return null
  const [x1, y1, x2, y2] = bbox
  const left = (x1 * scaleX).toFixed(1)
  const top  = (y1 * scaleY).toFixed(1)
  const width  = ((x2 - x1) * scaleX).toFixed(1)
  const height = ((y2 - y1) * scaleY).toFixed(1)
  const color = item.color || (item.severity === 'critical' ? '#ff4d4f' : item.severity === 'high' ? '#fa8c16' : '#52c41a')
  return (
    <div style={{
      position: 'absolute',
      left: `${left}px`, top: `${top}px`,
      width: `${width}px`, height: `${height}px`,
      border: `1.5px solid ${color}`,
      boxSizing: 'border-box',
      pointerEvents: 'none',
    }}>
      {item.label && (
        <span style={{
          position: 'absolute', top: -16, left: 0,
          fontSize: '0.58rem', background: 'rgba(0,0,0,0.75)',
          color, padding: '0 3px', whiteSpace: 'nowrap', lineHeight: '16px',
        }}>
          {item.label}
        </span>
      )}
    </div>
  )
}

function computeDisplayState(camera, latestFrame, streamSession, preferAnnotated, replayFrame) {
  if (replayFrame) return 'REPLAY_FRAME'
  if (!camera) return 'NO_FRAME'
  if (camera.status === 'disabled') return 'DISABLED'
  if (camera.status === 'error') return 'ERROR'
  if (camera.status === 'offline') return 'OFFLINE'
  const isRunning = streamSession?.state === 'running'
  const hasGoodFrame = latestFrame?.status === 'ok' && !latestFrame.stale
  const hasAnnotated = Boolean(latestFrame?.annotated_image_url)
  if (isRunning && hasGoodFrame) {
    return preferAnnotated && hasAnnotated ? 'LIVE_ANNOTATED' : 'LIVE'
  }
  if (hasGoodFrame) {
    return preferAnnotated && hasAnnotated ? 'ANNOTATED' : 'SNAPSHOT'
  }
  if (latestFrame?.status === 'ok' && latestFrame.stale) return 'STALE'
  if (camera.status === 'degraded') return 'STALE'
  return 'NO_FRAME'
}

export default function LiveVideoSurface({
  camera,
  latestFrame,
  streamSession,
  selected,
  onSelect,
  replayFrame = null,
}) {
  const containerRef = useRef(null)
  const [containerSize, setContainerSize] = useState({ w: 640, h: 360 })
  const [imgError, setImgError] = useState(false)
  const [imgKey, setImgKey] = useState(0)
  const [preferAnnotated, setPreferAnnotated] = useState(true)
  const [showOverlays, setShowOverlays] = useState(true)

  useEffect(() => {
    if (!containerRef.current) return
    const obs = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) setContainerSize({ w: width, h: height })
      }
    })
    obs.observe(containerRef.current)
    return () => obs.disconnect()
  }, [])

  useEffect(() => {
    setImgError(false)
    setImgKey(k => k + 1)
  }, [latestFrame?.frame_id, latestFrame?.timestamp, replayFrame])

  if (!camera && !replayFrame) return null

  const displayState = computeDisplayState(camera, latestFrame, streamSession, preferAnnotated, replayFrame)
  const frameW = latestFrame?.width || 640
  const frameH = latestFrame?.height || 640
  const scaleX = containerSize.w / frameW
  const scaleY = containerSize.h / frameH

  const isLive = displayState === 'LIVE' || displayState === 'LIVE_ANNOTATED'
  const useAnnotated = preferAnnotated && latestFrame?.annotated_image_url

  // Build URLs
  const mjpegUrl = latestFrame?.mjpeg_url
    ? `${API_BASE_URL}${latestFrame.mjpeg_url}`
    : camera ? `${API_BASE_URL}/api/cameras/${encodeURIComponent(camera.camera_id)}/mjpeg` : null

  let imageUrl = null
  if (replayFrame) {
    imageUrl = replayFrame.snapshot_path
      ? `${API_BASE_URL}/api/cameras/${encodeURIComponent(replayFrame.camera_id)}/latest-frame/image`
      : null
  } else if (useAnnotated && latestFrame?.annotated_image_url) {
    imageUrl = `${API_BASE_URL}${latestFrame.annotated_image_url}`
  } else if (latestFrame?.image_url) {
    imageUrl = `${API_BASE_URL}${latestFrame.image_url}`
  } else if (camera) {
    imageUrl = `${API_BASE_URL}/api/cameras/${encodeURIComponent(camera.camera_id)}/latest-frame/image`
  }

  const hasImage = (latestFrame?.status === 'ok' || replayFrame) && imageUrl && !imgError
  const overlayItems = showOverlays ? (latestFrame?.overlay_items || latestFrame?.overlays || []) : []
  // Phase 23: open-vocab detections as overlay items (shown in purple)
  const ovDetections = showOverlays && latestFrame?.open_vocab_detections
    ? latestFrame.open_vocab_detections.map(d => ({ ...d, color: '#a78bfa' }))
    : []

  return (
    <div
      onClick={() => onSelect && onSelect(camera)}
      style={{
        position: 'relative',
        background: '#080d16',
        border: selected ? '1.5px solid #1890ff' : '1px solid #1c2535',
        borderRadius: 8,
        overflow: 'hidden',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 220,
      }}
    >
      {/* Header bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 10px', background: 'rgba(0,0,0,0.5)', zIndex: 5, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 700, fontSize: '0.8rem', color: '#e6e6e6' }}>
            {camera?.name || replayFrame?.camera_id || 'Camera'}
          </span>
          <StatusBanner state={displayState} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Toggle overlays */}
          <button
            onClick={e => { e.stopPropagation(); setShowOverlays(v => !v) }}
            title={showOverlays ? 'Hide overlays' : 'Show overlays'}
            style={{
              background: showOverlays ? '#1890ff20' : 'none',
              border: `1px solid ${showOverlays ? '#1890ff' : '#374151'}`,
              color: showOverlays ? '#1890ff' : '#4b5563',
              borderRadius: 3, padding: '1px 5px', fontSize: '0.6rem', cursor: 'pointer',
            }}
          >
            OVL
          </button>
          {/* Toggle annotated */}
          {latestFrame?.annotated_image_url && (
            <button
              onClick={e => { e.stopPropagation(); setPreferAnnotated(v => !v) }}
              title={preferAnnotated ? 'Switch to raw frame' : 'Switch to annotated frame'}
              style={{
                background: preferAnnotated ? '#52c41a20' : 'none',
                border: `1px solid ${preferAnnotated ? '#52c41a' : '#374151'}`,
                color: preferAnnotated ? '#52c41a' : '#4b5563',
                borderRadius: 3, padding: '1px 5px', fontSize: '0.6rem', cursor: 'pointer',
              }}
            >
              ANN
            </button>
          )}
          {camera && <SeverityBadge severity={camera.riskSeverity || 'info'} compact />}
        </div>
      </div>

      {/* Video / image region */}
      <div ref={containerRef} style={{ position: 'relative', flex: 1, overflow: 'hidden', minHeight: 160 }}>
        {isLive && mjpegUrl ? (
          <img
            key={`mjpeg-${camera?.camera_id}`}
            src={mjpegUrl}
            alt={`${camera?.name} live`}
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            onError={() => {/* MJPEG unavailable — stay in LIVE state */}}
          />
        ) : hasImage ? (
          <img
            key={`snap-${camera?.camera_id}-${imgKey}`}
            src={imageUrl}
            alt={`${camera?.name} snapshot`}
            style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            onError={() => setImgError(true)}
          />
        ) : (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            color: '#374151', fontSize: '0.75rem', gap: 4,
          }}>
            <span style={{ fontSize: '1.5rem', opacity: 0.3 }}>▶</span>
            <span>RTSP · WebRTC · HLS</span>
            <span style={{ fontSize: '0.65rem', color: '#1f2937' }}>Live stream slot</span>
          </div>
        )}

        {/* JS overlay layer — detection/track boxes (raw frame only) */}
        {!useAnnotated && overlayItems.length > 0 && (
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 4 }}>
            {overlayItems.map((item, i) => (
              <OverlayBox key={i} item={item} scaleX={scaleX} scaleY={scaleY} />
            ))}
          </div>
        )}
        {/* Phase 23: open-vocab detection overlays (purple) */}
        {ovDetections.length > 0 && (
          <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 5 }}>
            {ovDetections.map((item, i) => (
              <OverlayBox key={`ov-${i}`} item={item} scaleX={scaleX} scaleY={scaleY} />
            ))}
          </div>
        )}

        {/* Status overlays for non-active states */}
        {(displayState === 'OFFLINE' || displayState === 'ERROR' || displayState === 'DISABLED') && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 6,
            background: displayState === 'ERROR' ? 'rgba(60,0,0,0.6)' : 'rgba(0,0,0,0.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <StatusBanner state={displayState} />
          </div>
        )}
        {displayState === 'STALE' && (
          <div style={{
            position: 'absolute', bottom: 6, right: 6, zIndex: 5,
            fontSize: '0.6rem', color: '#fa8c16', background: 'rgba(0,0,0,0.7)',
            padding: '1px 5px', borderRadius: 3,
          }}>
            {latestFrame?.age_seconds != null ? `${latestFrame.age_seconds}s ago` : 'stale'}
          </div>
        )}
        {displayState === 'REPLAY_FRAME' && replayFrame && (
          <div style={{
            position: 'absolute', bottom: 6, left: 6, zIndex: 5,
            fontSize: '0.6rem', color: '#9b59b6', background: 'rgba(0,0,0,0.7)',
            padding: '1px 5px', borderRadius: 3,
          }}>
            frame #{replayFrame.frame_id ?? '—'}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        padding: '4px 10px', background: 'rgba(0,0,0,0.4)', fontSize: '0.62rem', color: '#4b5563',
        flexShrink: 0, zIndex: 5,
      }}>
        <span>{camera?.zone || 'no zone'}</span>
        <span>{camera?.source_type}</span>
        {latestFrame?.detections?.length > 0 && (
          <span style={{ color: '#fa8c16' }}>{latestFrame.detections.length} det</span>
        )}
        {latestFrame?.age_seconds != null && displayState !== 'STALE' && (
          <span>{latestFrame.age_seconds}s</span>
        )}
      </div>
    </div>
  )
}
