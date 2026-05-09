import HeatmapPanel from '../components/dashboard/HeatmapPanel'
import TimelinePanel from '../components/dashboard/TimelinePanel'

export default function ForensicsPage() {
  return (
    <div className="page-grid two-column">
      <TimelinePanel />
      <HeatmapPanel />
    </div>
  )
}
