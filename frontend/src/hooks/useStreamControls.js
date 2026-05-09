import { useCallback, useState } from 'react'
import { pauseCamera, restartCamera, resumeCamera, startCamera, stopCamera } from '../api/camerasApi'
import { normalizeError } from '../api/client'

export function useStreamControls({ onSuccess } = {}) {
  const [busyCameraId, setBusyCameraId] = useState(null)
  const [error, setError] = useState(null)

  const run = useCallback(async (cameraId, apiFn) => {
    setBusyCameraId(cameraId)
    setError(null)
    try {
      const result = await apiFn(cameraId)
      if (onSuccess) onSuccess(cameraId, result)
      return result
    } catch (err) {
      setError(normalizeError(err))
      return null
    } finally {
      setBusyCameraId(null)
    }
  }, [onSuccess])

  return {
    start: cameraId => run(cameraId, startCamera),
    stop: cameraId => run(cameraId, stopCamera),
    pause: cameraId => run(cameraId, pauseCamera),
    resume: cameraId => run(cameraId, resumeCamera),
    restart: cameraId => run(cameraId, restartCamera),
    busyCameraId,
    error,
  }
}
