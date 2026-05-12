import { useEffect } from 'react'
import CameraGraphPanel from '../components/investigation/CameraGraphPanel'
import InvestigationSafetyBadge from '../components/investigation/InvestigationSafetyBadge'
import PathReconstructionPanel from '../components/investigation/PathReconstructionPanel'
import { useAuth } from '../hooks/useAuth'
import { useInvestigation } from '../hooks/useInvestigation'

export default function InvestigationWorkspacePage() {
  const auth = useAuth()
  const {
    hypotheses,
    cameraGraph,
    loading,
    reconstructing,
    error,
    reconstructPath,
    loadHypotheses,
    reviewHypothesis,
    loadCameraGraph,
  } = useInvestigation()

  useEffect(() => {
    loadHypotheses()
    loadCameraGraph()
  }, [loadHypotheses, loadCameraGraph])

  return (
    <div className="flex h-full flex-col bg-gray-50">
      <div className="flex items-center justify-between border-b bg-white px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Investigation Workspace</h1>
          <p className="text-xs text-gray-500">
            Candidate paths may include fixed cameras, uploaded video, and simulated aerial observations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {auth.hasPermission('drone:read') ? (
            <button
              type="button"
              className="rounded border px-3 py-2 text-xs text-gray-700"
              onClick={() => {
                window.location.hash = 'drone-simulation'
              }}
            >
              Open Drone Source
            </button>
          ) : null}
          <InvestigationSafetyBadge className="max-w-lg" />
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-72 flex-shrink-0 overflow-y-auto border-r bg-white">
          <div className="border-b px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
            Camera Graph
          </div>
          <div className="p-3">
            <CameraGraphPanel graph={cameraGraph} onLoad={loadCameraGraph} />
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto">
          <PathReconstructionPanel
            onReconstruct={reconstructPath}
            hypotheses={hypotheses}
            onReview={reviewHypothesis}
            reconstructing={reconstructing}
            error={error}
          />
        </main>
      </div>

      {loading ? (
        <div className="border-t bg-white px-4 py-2 text-xs text-gray-400">Loading...</div>
      ) : null}
    </div>
  )
}
