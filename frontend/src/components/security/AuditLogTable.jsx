import { formatDateTime } from '../../utils/time'

export default function AuditLogTable({ logs, loading, error, filters, onFiltersChange, onRefresh }) {
  function updateFilter(key, value) {
    onFiltersChange({ ...filters, [key]: value || undefined })
  }

  return (
    <section className="panel security-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Audit</p>
          <h2>Operator Audit Logs</h2>
        </div>
        <button type="button" className="text-button" onClick={onRefresh}>Refresh</button>
      </div>
      <div className="filter-row">
        <input
          aria-label="Filter by action"
          placeholder="Action"
          value={filters.action || ''}
          onChange={event => updateFilter('action', event.target.value)}
        />
        <input
          aria-label="Filter by user"
          placeholder="User"
          value={filters.user_id || ''}
          onChange={event => updateFilter('user_id', event.target.value)}
        />
        <input
          aria-label="Filter by resource"
          placeholder="Resource"
          value={filters.resource_type || ''}
          onChange={event => updateFilter('resource_type', event.target.value)}
        />
      </div>
      {error && <div className="form-error">{error}</div>}
      {loading ? (
        <div className="muted">Loading audit logs...</div>
      ) : (
        <div className="table-scroll">
          <table className="security-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.audit_id}>
                  <td>{formatDateTime(log.timestamp)}</td>
                  <td>{log.username || 'system'}</td>
                  <td>{log.action}</td>
                  <td>{[log.resource_type, log.resource_id].filter(Boolean).join(': ') || 'N/A'}</td>
                  <td>
                    <span className={`state-chip ${log.success ? 'health-normal' : 'status-error'}`}>
                      {log.success ? 'success' : 'failure'}
                    </span>
                  </td>
                  <td>{log.detail || ''}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan="6" className="muted">No audit events found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
