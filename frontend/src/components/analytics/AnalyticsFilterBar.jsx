import { RefreshCw, Search, ShieldCheck } from 'lucide-react'

const WINDOW_OPTIONS = [
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
]

const BUCKET_OPTIONS = [
  { value: '5m', label: '5m buckets' },
  { value: '15m', label: '15m buckets' },
  { value: '1h', label: '1h buckets' },
  { value: '1d', label: '1d buckets' },
]

export default function AnalyticsFilterBar({ filters, onChange, onRefresh, loading, status }) {
  const degradedSources = Object.entries(status || {}).filter(([, value]) => value !== 'healthy').length

  return (
    <section className="panel analytics-filter-panel">
      <div className="analytics-filter-row">
        <label>
          <span>Window</span>
          <select value={filters.window} onChange={event => onChange({ window: event.target.value })}>
            {WINDOW_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          <span>Bucket</span>
          <select value={filters.bucket} onChange={event => onChange({ bucket: event.target.value })}>
            {BUCKET_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          <span>Camera</span>
          <input value={filters.camera_id} onChange={event => onChange({ camera_id: event.target.value })} placeholder="cam_01" />
        </label>
        <label>
          <span>Severity</span>
          <select value={filters.severity} onChange={event => onChange({ severity: event.target.value })}>
            <option value="">All severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </label>
        <label className="analytics-search-field">
          <span>Search</span>
          <div className="analytics-search-input">
            <Search size={14} />
            <input value={filters.q} onChange={event => onChange({ q: event.target.value })} placeholder="review notes, cameras, tags" />
          </div>
        </label>
        <button type="button" className="primary-button analytics-refresh-button" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={14} />
          <span>{loading ? 'Refreshing' : 'Refresh'}</span>
        </button>
      </div>

      <div className="analytics-filter-meta">
        <div className="analytics-filter-meta-item">
          <ShieldCheck size={14} />
          <span>Language remains operator-safe: possible incident, possible match, requires review.</span>
        </div>
        <span className={`state-chip ${degradedSources > 0 ? 'health-degraded' : 'health-normal'}`}>
          {degradedSources > 0 ? `${degradedSources} degraded sources` : 'All analytics sources healthy'}
        </span>
      </div>
    </section>
  )
}
