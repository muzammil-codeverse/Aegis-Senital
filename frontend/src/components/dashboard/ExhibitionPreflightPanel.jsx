import { useMemo, useState } from 'react'

const RESULT_CLASS = {
  PASSED: 'health-normal',
  PARTIALLY_PASSED: 'health-degraded',
  FAILED: 'status-error',
  RUNNING: 'health-degraded',
  NOT_STARTED: '',
  CANCELLED: '',
}

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

function displayValue(value) {
  return String(value || 'UNKNOWN').replace(/_/g, ' ')
}

function formatDate(value) {
  if (!value) return 'No run recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString([], { hour12: false })
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

function Badge({ value, classMap = STATE_CLASS }) {
  const normalized = value || 'UNKNOWN'
  return <span className={`state-chip ${classMap[normalized] || ''}`.trim()}>{displayValue(normalized)}</span>
}

function recommendationsFor(run) {
  return Array.isArray(run?.recommendations) ? run.recommendations : []
}

function resultsFor(run) {
  return Array.isArray(run?.results) ? run.results : []
}

export default function ExhibitionPreflightPanel({
  latestRun = null,
  summary = null,
  loading = false,
  runningMode = null,
  error = null,
  onRunQuick,
  onRunExhibition,
  onRefresh,
}) {
  const [groupFilter, setGroupFilter] = useState('all')
  const results = resultsFor(latestRun)
  const groups = useMemo(
    () => ['all', ...Array.from(new Set(results.map(result => result.group).filter(Boolean))).sort()],
    [results],
  )
  const visibleResults = useMemo(() => {
    if (groupFilter === 'all') return results
    return results.filter(result => result.group === groupFilter)
  }, [groupFilter, results])

  const openAiResult = results.find(result => result.capability_id === 'llm_osint')
  const openAiMissing = openAiResult?.metadata?.openai_key_present === false || /OPENAI_API_KEY missing/i.test(openAiResult?.reason || '')
  const status = latestRun?.overall_status || summary?.overall_status || 'NOT_STARTED'
  const byState = summary?.by_state || {}

  return (
    <section className="panel exhibition-preflight-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Mission Readiness</p>
          <h2>Exhibition Preflight</h2>
        </div>
        <div className="button-row">
          <Badge value={status} classMap={RESULT_CLASS} />
          <button type="button" className="text-button" onClick={onRefresh} disabled={loading || Boolean(runningMode)}>
            Refresh
          </button>
          <button type="button" className="text-button" onClick={onRunQuick} disabled={loading || Boolean(runningMode)}>
            {runningMode === 'QUICK' ? 'Running Quick' : 'Run Quick'}
          </button>
          <button type="button" className="text-button" onClick={onRunExhibition} disabled={loading || Boolean(runningMode)}>
            {runningMode === 'EXHIBITION' ? 'Running Exhibition' : 'Run Exhibition'}
          </button>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}
      {openAiMissing && (
        <p className="warning-text">
          OSINT / LLM enrichment provider not configured — OPENAI_API_KEY is absent. Core demo, camera tracking, fusion, and drone mission continue normally. Only LLM-generated case summaries and OSINT enrichment are affected.
        </p>
      )}

      <div className="metric-strip" style={{ marginBottom: 12 }}>
        <SummaryTile label="Last Run" value={displayValue(status)} detail={formatDate(latestRun?.completed_at || latestRun?.started_at)} />
        <SummaryTile label="Duration" value={`${latestRun?.duration_ms || summary?.duration_ms || 0} ms`} detail={latestRun?.mode || summary?.mode || 'No mode'} />
        <SummaryTile label="Ready" value={byState.READY || 0} detail="Ready for exhibition path" />
        <SummaryTile label="Cold" value={(byState.COLD || 0) + (byState.REGISTERED || 0)} detail="Core capability awaiting preflight" />
        <SummaryTile label="Degraded" value={byState.DEGRADED || 0} detail="Operator action" />
        <SummaryTile label="Faulted" value={byState.FAULTED || 0} detail="Blocking review" />
      </div>

      {Array.isArray(latestRun?.blocking_failures) && latestRun.blocking_failures.length > 0 && (
        <div className="preflight-alert status-error">
          <strong>Blocking foundational failure</strong>
          <ul>
            {latestRun.blocking_failures.map(item => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}

      {Array.isArray(latestRun?.warnings) && latestRun.warnings.length > 0 && (
        <div className="preflight-alert">
          <strong>Warnings</strong>
          <ul>
            {latestRun.warnings.slice(0, 8).map(item => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}

      {recommendationsFor(latestRun).length > 0 && (
        <div className="preflight-alert">
          <strong>Recommended Actions</strong>
          <ul>
            {recommendationsFor(latestRun).slice(0, 8).map(item => (
              <li key={`${item.capability_id || 'system'}-${item.message}`}>
                {item.capability_id ? `${item.capability_id}: ` : ''}{item.action || item.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="filter-row" style={{ gridTemplateColumns: 'minmax(0, 1fr)', marginBottom: 12 }}>
        <select aria-label="Filter preflight capabilities by group" value={groupFilter} onChange={event => setGroupFilter(event.target.value)}>
          {groups.map(group => (
            <option key={group} value={group}>{group === 'all' ? 'All capability groups' : displayValue(group)}</option>
          ))}
        </select>
      </div>

      <div className="table-shell">
        <table className="uploaded-video-table">
          <thead>
            <tr>
              <th>Capability</th>
              <th>Group</th>
              <th>State</th>
              <th>Level</th>
              <th>Blocking</th>
              <th>Readiness</th>
            </tr>
          </thead>
          <tbody>
            {visibleResults.map(result => (
              <tr key={result.capability_id}>
                <td>
                  <strong>{result.name || result.capability_id}</strong>
                  <span className="table-subtext">{result.capability_id}</span>
                </td>
                <td>{displayValue(result.group)}</td>
                <td><Badge value={result.state} /></td>
                <td>Level {result.check_level || 1}</td>
                <td>{result.blocking ? 'Yes' : 'No'}</td>
                <td>
                  <span>{result.reason || 'Core capability awaiting preflight'}</span>
                  {Array.isArray(result.recommendations) && result.recommendations.length > 0 && (
                    <span className="table-subtext">{result.recommendations[0]}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!loading && results.length === 0 && (
        <p className="muted" style={{ marginTop: 10 }}>Core capability awaiting preflight.</p>
      )}
    </section>
  )
}

