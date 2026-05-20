import { Command, Search } from 'lucide-react'
import { formatDateTime } from '../../utils/time'
import UserMenu from '../auth/UserMenu'

export default function CommandTopBar({
  pageMeta,
  websocketStatus,
  lastMessageAt,
  reconnectCount,
  runtimeStatus,
  onOpenPalette,
}) {
  return (
    <header className="command-topbar">
      <div>
        <p className="eyebrow">Unified Command Center</p>
        <h1>{pageMeta?.label || 'Dashboard'}</h1>
        <p className="command-topbar__description">{pageMeta?.description || 'Operational overview'}</p>
      </div>
      <div className="command-topbar__actions">
        <button type="button" className="command-action-button" onClick={onOpenPalette}>
          <Search size={14} />
          Search
          <span className="command-action-button__hint"><Command size={12} />K</span>
        </button>
        <div className={`command-topbar__pill tone-${runtimeStatus?.overall || 'demo_ready'}`}>
          Runtime {runtimeStatus?.overall || 'Demo Ready'}
        </div>
        <div className={`command-topbar__pill tone-${websocketStatus && websocketStatus !== 'unknown' ? websocketStatus : 'polling'}`}>
          Alerts WS {websocketStatus && websocketStatus !== 'unknown' ? websocketStatus : 'Polling'}
        </div>
        <div className="command-topbar__meta">
          <span>Last alert</span>
          <strong>{lastMessageAt ? formatDateTime(lastMessageAt) : 'N/A'}</strong>
        </div>
        <div className="command-topbar__meta">
          <span>Reconnects</span>
          <strong>{reconnectCount ?? 0}</strong>
        </div>
        <UserMenu />
      </div>
    </header>
  )
}
