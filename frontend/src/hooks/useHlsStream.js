import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config'
import { getHlsPlaylistUrl } from '../api/streamingApi'

export function useHlsStream(cameraId, videoRef, { enabled = true } = {}) {
  const [mode, setMode] = useState('idle')
  const [url, setUrl] = useState(null)

  useEffect(() => {
    if (!enabled || !cameraId || !videoRef?.current) {
      setMode('idle')
      setUrl(null)
      return undefined
    }
    const video = videoRef.current
    const playlistUrl = `${API_BASE_URL}${getHlsPlaylistUrl(cameraId)}`
    setUrl(playlistUrl)

    if (typeof video.canPlayType !== 'function' || !video.canPlayType('application/vnd.apple.mpegurl')) {
      setMode('unsupported')
      return undefined
    }

    video.srcObject = null
    video.src = playlistUrl
    video.play?.().catch(() => {})
    setMode('hls')
    return () => {
      video.pause?.()
      video.removeAttribute('src')
      video.load?.()
    }
  }, [cameraId, enabled, videoRef])

  return { mode, url }
}
