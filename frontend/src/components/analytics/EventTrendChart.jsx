import { format } from 'date-fns'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import EmptyState from '../common/EmptyState'

function formatBucketLabel(value) {
  if (!value) return 'N/A'
  const date = new Date(value)
  return format(date, 'MMM d HH:mm')
}

export default function EventTrendChart({ eventTimeseries = [], eventsByType = [] }) {
  const timeseries = eventTimeseries.map(item => ({
    ...item,
    label: formatBucketLabel(item.bucket_start),
  }))

  return (
    <section className="panel analytics-panel analytics-span-8">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Event Intelligence</p>
          <h2>Operational Event Trends</h2>
        </div>
        <span className="count-pill">{eventsByType.length} event classes</span>
      </div>
      {timeseries.length === 0 ? <EmptyState message="No event history available for the selected window." /> : (
        <div className="analytics-chart-stack">
          <div className="analytics-chart-frame">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="analyticsEventsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#25d0c8" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#25d0c8" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" />
                <XAxis dataKey="label" stroke="#8492a6" minTickGap={28} />
                <YAxis stroke="#8492a6" />
                <Tooltip />
                <Area type="monotone" dataKey="total_events" stroke="#25d0c8" fill="url(#analyticsEventsFill)" strokeWidth={2} />
                <Area type="monotone" dataKey="critical_events" stroke="#ff5c6c" fill="rgba(255,92,108,0.12)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="analytics-chart-frame">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={eventsByType.slice(0, 8)}>
                <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" vertical={false} />
                <XAxis dataKey="event_type" stroke="#8492a6" tick={{ fontSize: 11 }} />
                <YAxis stroke="#8492a6" />
                <Tooltip />
                <Bar dataKey="count" fill="#25d0c8" radius={[4, 4, 0, 0]} />
                <Bar dataKey="critical_count" fill="#ff5c6c" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  )
}
