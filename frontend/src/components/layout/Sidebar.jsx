const NAV_ITEMS = [
  { id: 'dashboard', label: 'Command' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'incidents', label: 'Incidents' },
  { id: 'system', label: 'System' },
  { id: 'forensics', label: 'Forensics' },
]

export default function Sidebar({ currentPage, onNavigate }) {
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
        {NAV_ITEMS.map(item => (
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
