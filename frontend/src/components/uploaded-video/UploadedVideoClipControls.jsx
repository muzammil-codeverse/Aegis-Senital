import { useState } from 'react'
import { fetchUploadedVideoClipBlob } from '../../api/uploadedVideoApi'

export default function UploadedVideoClipControls({ sessionId, eventId, replayClip }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!replayClip?.hash_sha256) {
    return <p className="muted">Replay clip not generated for this event.</p>
  }

  const integrity = replayClip.integrity_status || 'pending'
  const badgeClass =
    integrity === 'verified' ? 'count-pill status-open' : 'count-pill severity-medium'

  const runDownload = async () => {
    setBusy(true)
    setError(null)
    try {
      const blob = await fetchUploadedVideoClipBlob(sessionId, eventId)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${eventId}.mp4`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err?.message || 'Download failed')
    } finally {
      setBusy(false)
    }
  }

  const runPlay = async () => {
    setBusy(true)
    setError(null)
    try {
      const blob = await fetchUploadedVideoClipBlob(sessionId, eventId)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setError(err?.message || 'Playback failed')
    } finally {
      setBusy(false)
    }
  }

  const copyHash = async () => {
    try {
      await navigator.clipboard.writeText(replayClip.hash_sha256)
    } catch {
      setError('Unable to copy hash')
    }
  }

  return (
    <div className="uploaded-video-clip-controls compact">
      <div className="button-row">
        <span className={badgeClass} title={replayClip.hash_sha256}>
          {integrity}
        </span>
        <button type="button" className="ghost-button" disabled={busy} onClick={runPlay}>
          Play
        </button>
        <button type="button" className="ghost-button" disabled={busy} onClick={runDownload}>
          Save
        </button>
        <button type="button" className="ghost-button" onClick={copyHash}>
          Copy hash
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  )
}
