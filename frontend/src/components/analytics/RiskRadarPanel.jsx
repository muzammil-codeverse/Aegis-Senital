import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts'
import EmptyState from '../common/EmptyState'

export default function RiskRadarPanel({ cameraRisk = [] }) {
  const points = cameraRisk.slice(0, 5).map(item => ({
    camera: item.camera_id,
    risk: item.risk_score,
  }))

  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Risk Radar</p>
          <h2>Operational Attention Score</h2>
        </div>
      </div>
      {points.length === 0 ? <EmptyState message="No camera risk scores are available to chart." /> : (
        <div className="analytics-chart-frame">
          <ResponsiveContainer width="100%" height={260}>
            <RadarChart data={points}>
              <PolarGrid stroke="rgba(132, 146, 166, 0.16)" />
              <PolarAngleAxis dataKey="camera" stroke="#8492a6" tick={{ fontSize: 11 }} />
              <Radar name="Risk" dataKey="risk" stroke="#ff5c6c" fill="rgba(255,92,108,0.22)" fillOpacity={1} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
