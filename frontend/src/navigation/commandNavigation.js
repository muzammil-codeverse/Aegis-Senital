export const commandNavigation = [
  {
    group: 'Overview',
    items: [
      { id: 'dashboard', label: 'Dashboard', permission: 'camera:read', description: 'Unified operational dashboard', iconKey: 'LayoutDashboard', healthKey: 'system' },
      { id: 'analytics', label: 'Analytics', permission: 'analytics:read', description: 'Operational analytics and summaries', iconKey: 'BarChart3' },
      { id: 'system', label: 'System Health', permission: 'metrics:read', description: 'Subsystem health and readiness', iconKey: 'Activity', healthKey: 'system' },
    ],
  },
  {
    group: 'Live Operations',
    items: [
      { id: 'live-streams', label: 'Live Streams', permission: 'camera:read', description: 'Live camera and stream operations', iconKey: 'MonitorPlay' },
      { id: 'uploaded-video-analysis', label: 'Uploaded Video Analysis', permission: 'uploaded_video:read', description: 'Offline video review workflows', iconKey: 'Film' },
      { id: 'alerts', label: 'Alerts', permission: 'alert:read', description: 'Operational alert queue', iconKey: 'BellRing' },
      { id: 'incidents', label: 'Incidents', permission: 'incident:read', description: 'Investigated incidents and replay', iconKey: 'TriangleAlert' },
    ],
  },
  {
    group: 'Geospatial',
    items: [
      { id: 'map-operations', label: 'Map Operations', permission: 'gis:read', description: 'GIS overlays and spatial analysis', iconKey: 'Map', healthKey: 'gis' },
      { id: 'investigation', label: 'Investigation Workspace', permission: 'investigation:read', description: 'Path reconstruction and hypothesis review', iconKey: 'Route', healthKey: 'investigation' },
    ],
  },
  {
    group: 'Drone Operations',
    items: [
      { id: 'drone-operations', label: 'Drone Operations Hub', permission: 'drone:read', description: 'Operational drone command overview', iconKey: 'Radar', healthKey: 'droneSimulation' },
      { id: 'drone-simulation', label: 'Drone Simulation', permission: 'drone:read', description: 'Simulated aerial observation runtime', iconKey: 'Plane', healthKey: 'droneSimulation' },
      { id: 'drone-mission-planner', label: 'Drone Mission Planner', permission: 'drone:read', description: 'Mission planning and execution', iconKey: 'MapPinned', healthKey: 'droneMission' },
      { id: 'drone-fusion', label: 'Drone Fusion', permission: 'drone_fusion:read', description: 'Cross-source drone and fixed camera fusion', iconKey: 'GitMerge', healthKey: 'droneFusion' },
    ],
  },
  {
    group: 'Intelligence',
    items: [
      { id: 'cases', label: 'Cases', permission: 'case:read', description: 'Case review and evidence workflows', iconKey: 'FolderKanban' },
      { id: 'identities', label: 'Identity', permission: 'identity:read', description: 'Identity candidates and registry', iconKey: 'Fingerprint' },
      { id: 'osint-enrichment', label: 'OSINT Enrichment', permission: 'osint:read', description: 'Manual enrichment and source review', iconKey: 'Globe' },
      { id: 'model-governance', label: 'Model Governance', permission: 'model:read', description: 'Model limitations, drift, and blockers', iconKey: 'ShieldCheck', healthKey: 'modelGovernance' },
    ],
  },
]

export const commandRouteIndex = Object.fromEntries(
  commandNavigation.flatMap(group => group.items.map(item => [item.id, item])),
)

export const commandRouteIds = Object.keys(commandRouteIndex)

export const commandPagePermissions = Object.fromEntries(
  commandNavigation.flatMap(group => group.items.map(item => [item.id, item.permission])),
)

export function getCommandPageMeta(pageId) {
  return commandRouteIndex[pageId] || commandRouteIndex.dashboard
}

export function getVisibleCommandNavigation(hasPermission) {
  return commandNavigation
    .map(group => ({
      ...group,
      items: group.items.filter(item => hasPermission(item.permission)),
    }))
    .filter(group => group.items.length > 0)
}
