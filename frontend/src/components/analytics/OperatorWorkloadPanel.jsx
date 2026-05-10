import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import EmptyState from '../common/EmptyState'

export default function OperatorWorkloadPanel({ operatorWorkload = [] }) {
  const rows = operatorWorkload.slice(0, 8)

  return (
    <section className="panel analytics-panel analytics-span-4">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Operator Workload</p>
          <h2>Assignments and Backlog</h2>
        </div>
        <span className="count-pill">{rows.length} operators</span>
      </div>
      {rows.length === 0 ? <EmptyState message="No operator workload records are available." /> : (
        <div className="analytics-chart-frame">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={rows} layout="vertical" margin={{ left: 18 }}>
              <CartesianGrid stroke="rgba(132, 146, 166, 0.12)" horizontal={false} />
              <XAxis type="number" stroke="#8492a6" />
              <YAxis type="category" dataKey="operator_id" stroke="#8492a6" width={72} />
              <Tooltip />
              <Bar dataKey="open_assigned_cases" fill="#25d0c8" radius={[0, 4, 4, 0]} />
              <Bar dataKey="review_backlog" fill="#ff5c6c" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
