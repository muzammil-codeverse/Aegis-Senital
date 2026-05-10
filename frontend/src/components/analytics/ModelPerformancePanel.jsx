import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatNumber, formatPercent } from '../../utils/formatters'
import EmptyState from '../common/EmptyState'

export default function ModelPerformancePanel({ modelPerformance = [], identitySummary, openVocabSummary, systemPerformance }) {
  return (
    <section className="panel analytics-panel analytics-span-5">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Model Performance</p>
          <h2>Latency, Confidence, and Auxiliary Activity</h2>
        </div>
        <span className="count-pill">{modelPerformance.length} model summaries</span>
      </div>
      <div className="analytics-mini-grid">
        <article className="analytics-mini-tile"><span>Possible matches</span><strong>{formatNumber(identitySummary?.possible_matches || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>ReID review queue</span><strong>{formatNumber(identitySummary?.review_required_matches || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Open-vocab hits</span><strong>{formatNumber(openVocabSummary?.threat_hits || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>GPU status</span><strong>{systemPerformance?.gpu_status || 'unknown'}</strong></article>
      </div>
      {modelPerformance.length === 0 ? <EmptyState message="No model performance summaries are available yet." /> : (
        <div className="analytics-chart-frame">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={modelPerformance}>
              <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" vertical={false} />
              <XAxis dataKey="display_name" stroke="#8492a6" tick={{ fontSize: 11 }} />
              <YAxis stroke="#8492a6" />
              <Tooltip />
              <Bar dataKey="avg_latency_ms" fill="#25d0c8" radius={[4, 4, 0, 0]} />
              <Bar dataKey="p95_latency_ms" fill="#f2b84b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="analytics-inline-list">
            {modelPerformance.map(model => (
              <article key={model.model_key} className="analytics-inline-card">
                <strong>{model.display_name}</strong>
                <span>{model.status}</span>
                <em>Avg conf {model.avg_confidence != null ? formatPercent(model.avg_confidence) : 'N/A'}</em>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
