import { useMemo } from 'react'

export function useSystemHealth(metrics = {}, apiError = null, stale = false) {
  return useMemo(() => {
    const reasons = []
    const queueOverflows = Number(metrics.queue_overflows ?? metrics.queue_overflow_count ?? 0)
    const droppedFrames = Number(metrics.frames_dropped ?? 0)
    const circuitTrips = Number(metrics.circuit_breaker_trips ?? metrics.stream_circuit_breaks ?? 0)
    const notificationFailures = Number(metrics.notification_failures ?? 0)
    const segmentationFailures = Number(metrics.segmentation_failures_total ?? 0)
    const segmentationUnavailable = Number(metrics.segmentation_provider_unavailable_total ?? 0)
    const websocketClients = Number(metrics.websocket_clients ?? 0)

    if (apiError) reasons.push('metrics service unavailable')
    if (stale) reasons.push('metrics are stale')
    if (queueOverflows > 0) reasons.push('queue overflow observed')
    if (circuitTrips > 0) reasons.push('circuit breaker activity')
    if (notificationFailures > 0) reasons.push('notification failures')
    if (droppedFrames > 0) reasons.push('dropped frames')
    if (segmentationFailures > 0) reasons.push('segmentation failures')
    if (segmentationUnavailable > 0) reasons.push('segmentation provider unavailable')

    let status = 'normal'
    if (apiError || circuitTrips > 0 || queueOverflows > 10) {
      status = 'critical'
    } else if (stale || droppedFrames > 0 || notificationFailures > 0 || queueOverflows > 0 || segmentationFailures > 0 || segmentationUnavailable > 0) {
      status = 'degraded'
    }

    const health = {
      status,
      reasons,
      websocketClients,
      generatedAt: metrics.generated_at ?? metrics.generatedAt ?? null,
    }

    return health
  }, [apiError, metrics, stale])
}
