import {
  Activity,
  BarChart3,
  BellRing,
  Film,
  Fingerprint,
  FolderKanban,
  GitMerge,
  Globe,
  LayoutDashboard,
  Map,
  MapPinned,
  MonitorPlay,
  Plane,
  Radar,
  Route,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'

const ICONS = {
  Activity,
  BarChart3,
  BellRing,
  Film,
  Fingerprint,
  FolderKanban,
  GitMerge,
  Globe,
  LayoutDashboard,
  Map,
  MapPinned,
  MonitorPlay,
  Plane,
  Radar,
  Route,
  ShieldCheck,
  TriangleAlert,
}

export default function CommandSidebar({ currentPage, navigation, onNavigate, runtimeStatus }) {
  return (
    <aside className="command-sidebar">
      <div className="command-sidebar__brand">
        <div className="command-sidebar__mark">AS</div>
        <div>
          <div className="brand-title">Aegis Sentinel</div>
          <div className="brand-subtitle">Command Center 2.0</div>
        </div>
      </div>

      <nav className="command-sidebar__nav" aria-label="Primary navigation">
        {navigation.map(group => (
          <section key={group.group} className="command-sidebar__group">
            <p className="command-sidebar__group-title">{group.group}</p>
            <div className="command-sidebar__group-items">
              {group.items.map(item => {
                const Icon = ICONS[item.iconKey] || LayoutDashboard
                const health = item.healthKey ? runtimeStatus?.byKey?.[item.healthKey] : null
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`command-nav-item ${currentPage === item.id ? 'active' : ''}`}
                    onClick={() => onNavigate(item.id)}
                  >
                    <span className="command-nav-item__icon"><Icon size={16} /></span>
                    <span className="command-nav-item__text">
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                    {health ? <span className={`mini-status-pill tone-${health.status}`}>{health.status}</span> : null}
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </nav>

      <div className="command-sidebar__footer">
        <span className="label">Mode</span>
        <strong>Operational review</strong>
        <p>All drone activity shown here is simulated when sourced from the simulator.</p>
      </div>
    </aside>
  )
}
