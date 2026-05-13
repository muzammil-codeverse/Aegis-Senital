import { normalizeItemResponse, normalizeListResponse, request } from './client'

export const droneSimulationApi = {
  getStatus: async () => normalizeItemResponse(await request({ method: 'GET', url: '/api/drone-simulation/status' })),
  getRuntime: async () => normalizeItemResponse(await request({ method: 'GET', url: '/api/drone-simulation/runtime' })),
  getRuntimeStatus: async () => normalizeItemResponse(await request({ method: 'GET', url: '/api/drone-simulation/runtime-status' })),
  launchRuntime: async prefer => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/runtime/launch', data: { prefer } })),
  runMissionDemo: async mission => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/missions/run-demo', data: { mission } })),
  listCameras: async () => normalizeListResponse(await request({ method: 'GET', url: '/api/drone-simulation/cameras' })),
  listEvents: async () => normalizeListResponse(await request({ method: 'GET', url: '/api/drone-simulation/events' })),
  startStream: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/stream/start' })),
  stopStream: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/stream/stop' })),
  startSession: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/start' })),
  stopSession: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/stop' })),
  getTelemetry: async () => normalizeItemResponse(await request({ method: 'GET', url: '/api/drone-simulation/telemetry' })),
  getFlightPath: async () => normalizeListResponse(await request({ method: 'GET', url: '/api/drone-simulation/flight-path' })),
  takeoff: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/commands/takeoff' })),
  land: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/commands/land' })),
  hover: async () => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/commands/hover' })),
  move: async payload => normalizeItemResponse(await request({ method: 'POST', url: '/api/drone-simulation/commands/move', data: payload })),
  getLatestFrame: async () => normalizeItemResponse(await request({ method: 'GET', url: '/api/drone-simulation/frame/latest' })),
  getCameraLatestFrame: async cameraName => normalizeItemResponse(await request({ method: 'GET', url: `/api/drone-simulation/cameras/${encodeURIComponent(cameraName)}/latest-frame` })),
}
