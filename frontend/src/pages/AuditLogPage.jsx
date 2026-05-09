import ProtectedRoute from '../components/auth/ProtectedRoute'
import AuditLogTable from '../components/security/AuditLogTable'
import UserManagementPanel from '../components/security/UserManagementPanel'
import { getAuditIntegrity } from '../api/auditApi'
import { useAuditLogs } from '../hooks/useAuditLogs'
import { useAuth } from '../hooks/useAuth'
import { useState } from 'react'

export default function AuditLogPage({ mode = 'audit' }) {
  const audit = useAuditLogs({ recent: true, limit: 200 })
  const { hasPermission } = useAuth()
  const [integrity, setIntegrity] = useState(null)

  if (mode === 'users') {
    return (
      <ProtectedRoute permission="admin">
        <div className="page-grid single-column">
          <UserManagementPanel />
        </div>
      </ProtectedRoute>
    )
  }

  return (
    <ProtectedRoute permission="audit:read">
      <div className="page-grid single-column">
        <section className="panel security-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Integrity</p>
              <h2>Audit Hash Chain</h2>
            </div>
            <button
              type="button"
              className="text-button"
              onClick={async () => setIntegrity(await getAuditIntegrity())}
            >
              Verify
            </button>
          </div>
          {integrity && (
            <div className={`state ${integrity.status === 'ok' ? 'health-normal' : 'state-error'}`}>
              <span>{integrity.checked_files} files checked</span>
              <strong>{integrity.status}</strong>
            </div>
          )}
        </section>
        <AuditLogTable
          logs={audit.logs}
          loading={audit.loading}
          error={audit.error}
          filters={audit.filters}
          onFiltersChange={audit.setFilters}
          onRefresh={() => audit.refresh()}
        />
        {hasPermission('admin') && <UserManagementPanel />}
      </div>
    </ProtectedRoute>
  )
}
