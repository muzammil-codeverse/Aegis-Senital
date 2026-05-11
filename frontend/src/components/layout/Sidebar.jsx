import { useAuth } from '../../hooks/useAuth'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Command', permission: 'camera:read' },
  { id: 'analytics', label: 'Analytics', permission: 'analytics:read' },
  { id: 'alerts', label: 'Alerts', permission: 'alert:read' },
  { id: 'incidents', label: 'Incidents', permission: 'incident:read' },
  { id: 'cases', label: 'Cases', permission: 'case:read' },
  { id: 'system', label: 'System', permission: 'metrics:read' },
  { id: 'forensics', label: 'Forensics', permission: 'forensics:read' },
  { id: 'identities', label: 'Identities', permission: 'identity:read' },
  { id: 'watchlist', label: 'Watchlist', permission: 'watchlist:read' },
  { id: 'uploaded-video-analysis', label: 'Uploaded Video', permission: 'uploaded_video:read' },
  { id: 'models', label: 'Models', permission: 'model:read' },
  { id: 'audit', label: 'Audit Logs', permission: 'audit:read' },
  { id: 'security', label: 'Security', permission: 'admin' },
]

export default function Sidebar({ currentPage, onNavigate }) {
  const { hasPermission } = useAuth()
  const visibleItems = NAV_ITEMS.filter(item => hasPermission(item.permission))
  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark">AS</div>
        <div>
          <div className="brand-title">Aegis Sentinel</div>
          <div className="brand-subtitle">Command Center</div>
        </div>
      </div>
      <nav className="nav-stack" aria-label="Primary navigation">
        {visibleItems.map(item => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className="label">Mode</span>
        <strong>Operations</strong>
      </div>
    </aside>
  )
}
