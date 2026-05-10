import { useState } from 'react'
import { normalizeError } from '../../api/client'
import { restartStream, startStream, stopStream } from '../../api/streamingApi'

export default function CameraStreamControls({ cameraId, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run(action) {
    if (!cameraId) return
    setBusy(true)
    setError(null)
    try {
      if (action === 'start') await startStream(cameraId)
      if (action === 'stop') await stopStream(cameraId)
      if (action === 'restart') await restartStream(cameraId)
      onChanged?.()
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="button-row">
        <button type="button" className="text-button" disabled={busy || !cameraId} onClick={() => run('start')}>Start</button>
        <button type="button" className="text-button" disabled={busy || !cameraId} onClick={() => run('stop')}>Stop</button>
        <button type="button" className="text-button" disabled={busy || !cameraId} onClick={() => run('restart')}>Restart</button>
      </div>
      {error && <div style={{ marginTop: 6, color: '#ff7875', fontSize: '0.72rem' }}>{error}</div>}
    </div>
  )
}
