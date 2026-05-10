import { format } from 'date-fns'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatNumber, formatPercent } from '../../utils/formatters'
import EmptyState from '../common/EmptyState'

export default function AnomalyTrendPanel({ anomalyTrends }) {
  const series = (anomalyTrends?.timeseries || []).map(item => ({
    ...item,
    label: format(new Date(item.bucket_start), 'MMM d HH:mm'),
  }))

  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Anomaly Review</p>
          <h2>VideoMAE Trendline</h2>
        </div>
        <span className="count-pill">{formatNumber(anomalyTrends?.total_anomalies || 0)} anomalies</span>
      </div>
      <div className="analytics-mini-grid">
        <article className="analytics-mini-tile"><span>Critical</span><strong>{formatNumber(anomalyTrends?.critical_anomalies || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Avg score</span><strong>{formatPercent(anomalyTrends?.avg_score || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Peak score</span><strong>{formatPercent(anomalyTrends?.max_score || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>False-positive feedback</span><strong>{formatNumber(anomalyTrends?.false_positive_feedback_total || 0)}</strong></article>
      </div>
      {series.length === 0 ? <EmptyState message="No anomaly windows were stored for the selected period." /> : (
        <div className="analytics-chart-frame">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={series}>
              <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" />
              <XAxis dataKey="label" stroke="#8492a6" minTickGap={28} />
              <YAxis stroke="#8492a6" />
              <Tooltip />
              <Line type="monotone" dataKey="total_events" stroke="#a78bfa" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="critical_events" stroke="#ff5c6c" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
