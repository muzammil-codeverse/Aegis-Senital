import { useMemo, useState } from 'react'

const STATE_CLASS = {
  READY: 'health-normal',
  ACTIVE: 'health-normal',
  COLD: 'health-degraded',
  REGISTERED: 'health-degraded',
  WARMING: 'health-degraded',
  RECOVERING: 'health-degraded',
  DEGRADED: 'health-degraded',
  FAULTED: 'status-error',
  DISABLED: '',
  UNKNOWN: '',
}

function displayState(state) {
  if (state === 'COLD') return 'Awaiting warmup'
  if (state === 'REGISTERED') return 'Registered'
  return state || 'UNKNOWN'
}

function formatDate(value) {
  if (!value) return 'Not checked'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString([], { hour12: false })
}

function capabilitySummaryValue(summary, key) {
  const value = summary?.[key]
  return Number.isFinite(value) ? value : 0
}

function SummaryTile({ label, value, detail }) {
  return (
    <article className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small style={{ color: 'var(--muted)' }}>{detail}</small>}
    </article>
  )
}

function StateBadge({ state }) {
  const normalized = state || 'UNKNOWN'
  return <span className={`state-chip ${STATE_CLASS[normalized] || ''}`.trim()}>{displayState(normalized)}</span>
}

export default function CapabilityHealthPanel({
  capabilities = [],
  summary = {},
  loading = false,
  error = null,
  onRefresh,
}) {
  const [category, setCategory] = useState('all')
  const [criticality, setCriticality] = useState('all')

  const categories = useMemo(
    () => ['all', ...Array.from(new Set(capabilities.map(item => item.category).filter(Boolean))).sort()],
    [capabilities],
  )
  const criticalities = useMemo(
    () => ['all', ...Array.from(new Set(capabilities.map(item => item.criticality).filter(Boolean))).sort()],
    [capabilities],
  )

  const visible = useMemo(() => capabilities.filter(item => (
    (category === 'all' || item.category === category) &&
    (criticality === 'all' || item.criticality === criticality)
  )), [capabilities, category, criticality])

  return (
    <section className="panel capability-health-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Capability Orchestration</p>
          <h2>Capability Health</h2>
        </div>
        <div className="button-row">
          <span className={`health-pill ${STATE_CLASS[summary?.overall_state] || ''}`.trim()}>
            {summary?.overall_state || 'UNKNOWN'}
          </span>
          <button type="button" className="text-button" onClick={onRefresh} disabled={loading}>
            {loading ? 'Refreshing' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="metric-strip" style={{ marginBottom: 12 }}>
        <SummaryTile label="Total" value={summary?.total || capabilities.length} detail="Registered capabilities" />
        <SummaryTile label="Ready" value={capabilitySummaryValue(summary, 'ready')} detail="Initialized" />
        <SummaryTile label="Cold" value={capabilitySummaryValue(summary, 'cold')} detail="Managed activation" />
        <SummaryTile label="Degraded" value={capabilitySummaryValue(summary, 'degraded')} detail="Operator review" />
        <SummaryTile label="Faulted" value={capabilitySummaryValue(summary, 'faulted')} detail="Recovery required" />
        <SummaryTile label="Active" value={capabilitySummaryValue(summary, 'active')} detail="Executing" />
      </div>

      <div className="filter-row" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', marginBottom: 12 }}>
        <select aria-label="Filter capabilities by category" value={category} onChange={event => setCategory(event.target.value)}>
          {categories.map(item => <option key={item} value={item}>{item === 'all' ? 'All categories' : item.replace(/_/g, ' ')}</option>)}
        </select>
        <select aria-label="Filter capabilities by criticality" value={criticality} onChange={event => setCriticality(event.target.value)}>
          {criticalities.map(item => <option key={item} value={item}>{item === 'all' ? 'All criticality levels' : item.replace(/_/g, ' ')}</option>)}
        </select>
      </div>

      <div className="table-shell">
        <table className="uploaded-video-table">
          <thead>
            <tr>
              <th>Capability</th>
              <th>State</th>
              <th>Category</th>
              <th>Criticality</th>
              <th>Activation</th>
              <th>Last checked</th>
              <th>Reason / last error</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(item => (
              <tr key={item.id}>
                <td>
                  <strong>{item.name || item.id}</strong>
                  <span className="table-subtext">{item.id}</span>
                </td>
                <td><StateBadge state={item.state} /></td>
                <td>{String(item.category || 'UNKNOWN').replace(/_/g, ' ')}</td>
                <td>{String(item.criticality || 'UNKNOWN').replace(/_/g, ' ')}</td>
                <td>{String(item.activation_mode || 'UNKNOWN').replace(/_/g, ' ')}</td>
                <td>{formatDate(item.last_checked_at)}</td>
                <td>
                  <span>{item.last_error || item.state_reason || 'Registered'}</span>
                  {Array.isArray(item.dependencies) && item.dependencies.length > 0 && (
                    <span className="table-subtext">Depends on: {item.dependencies.join(', ')}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && visible.length === 0 && (
        <p className="muted" style={{ marginTop: 10 }}>No capabilities match the current filters.</p>
      )}
    </section>
  )
}
