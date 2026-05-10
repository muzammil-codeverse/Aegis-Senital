import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../config'
import { normalizeError } from '../api/client'
import { createWebRTCOffer, stopWebRTCPreview } from '../api/streamingApi'

export function useWebRTCStream(cameraId, videoRef, { enabled = true } = {}) {
  const [mode, setMode] = useState('idle')
  const [error, setError] = useState(null)
  const [fallbackUrl, setFallbackUrl] = useState(null)

  useEffect(() => {
    if (!enabled || !cameraId || !videoRef?.current) {
      setMode('idle')
      setFallbackUrl(null)
      return undefined
    }
    if (typeof window === 'undefined' || typeof window.RTCPeerConnection !== 'function') {
      setMode('fallback')
      setFallbackUrl(`${API_BASE_URL}/api/streams/${encodeURIComponent(cameraId)}/mjpeg`)
      return undefined
    }

    let peer = null
    let disposed = false

    async function connect() {
      try {
        const localPeer = new window.RTCPeerConnection()
        peer = localPeer
        localPeer.addTransceiver('video', { direction: 'recvonly' })
        localPeer.ontrack = event => {
          const [stream] = event.streams || []
          if (videoRef.current && stream) {
            videoRef.current.srcObject = stream
            videoRef.current.play?.().catch(() => {})
          }
        }

        const offer = await localPeer.createOffer()
        await localPeer.setLocalDescription(offer)
        const response = await createWebRTCOffer(cameraId, {
          sdp: localPeer.localDescription?.sdp || offer.sdp,
          type: localPeer.localDescription?.type || offer.type,
        })
        const answer = response.item
        if (!answer || answer.status !== 'ok' || !answer.sdp) {
          setMode('fallback')
          setFallbackUrl(answer?.preview_url ? `${API_BASE_URL}${answer.preview_url}` : `${API_BASE_URL}/api/streams/${encodeURIComponent(cameraId)}/mjpeg`)
          await localPeer.close()
          return
        }
        await localPeer.setRemoteDescription({ type: answer.type || 'answer', sdp: answer.sdp })
        if (!disposed) {
          setMode('webrtc')
          setError(null)
        }
      } catch (err) {
        if (!disposed) {
          setMode('fallback')
          setFallbackUrl(`${API_BASE_URL}/api/streams/${encodeURIComponent(cameraId)}/mjpeg`)
          setError(normalizeError(err))
        }
      }
    }

    connect()

    return () => {
      disposed = true
      stopWebRTCPreview(cameraId).catch(() => {})
      if (peer) {
        try {
          peer.close()
        } catch (_) {}
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null
      }
    }
  }, [cameraId, enabled, videoRef])

  return { mode, error, fallbackUrl }
}
