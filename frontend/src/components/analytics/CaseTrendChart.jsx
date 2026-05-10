import { format } from 'date-fns'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatNumber } from '../../utils/formatters'
import EmptyState from '../common/EmptyState'

export default function CaseTrendChart({ caseSummary, caseTimeseries = [] }) {
  const points = caseTimeseries.map(item => ({
    ...item,
    label: format(new Date(item.bucket_start), 'MMM d HH:mm'),
  }))

  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Case Intelligence</p>
          <h2>Lifecycle Trends</h2>
        </div>
        <span className="count-pill">{formatNumber(caseSummary?.total_cases || 0)} cases</span>
      </div>
      <div className="analytics-mini-grid">
        <article className="analytics-mini-tile"><span>Open</span><strong>{formatNumber(caseSummary?.open_cases || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Resolved</span><strong>{formatNumber(caseSummary?.resolved_cases || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Review queue</span><strong>{formatNumber(caseSummary?.cases_requiring_review || 0)}</strong></article>
        <article className="analytics-mini-tile"><span>Avg resolution</span><strong>{caseSummary?.avg_resolution_hours != null ? `${caseSummary.avg_resolution_hours}h` : 'N/A'}</strong></article>
      </div>
      {points.length === 0 ? <EmptyState message="No case movement available in the selected window." /> : (
        <div className="analytics-chart-frame">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={points}>
              <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" />
              <XAxis dataKey="label" stroke="#8492a6" minTickGap={28} />
              <YAxis stroke="#8492a6" allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="opened_cases" stroke="#25d0c8" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="resolved_cases" stroke="#56d364" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="dismissed_cases" stroke="#f2b84b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
