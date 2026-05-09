import ProtectedRoute from '../components/auth/ProtectedRoute'
import AuditLogTable from '../components/security/AuditLogTable'
import UserManagementPanel from '../components/security/UserManagementPanel'
import { useAuditLogs } from '../hooks/useAuditLogs'
import { useAuth } from '../hooks/useAuth'

export default function AuditLogPage({ mode = 'audit' }) {
  const audit = useAuditLogs({ recent: true, limit: 200 })
  const { hasPermission } = useAuth()

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
