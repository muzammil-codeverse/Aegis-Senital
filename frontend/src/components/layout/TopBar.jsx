import { formatDateTime } from '../../utils/time'

export default function TopBar({ websocketStatus, lastMessageAt, reconnectCount }) {
  const wsLabel = websocketStatus || 'unknown'
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Live Intelligence Runtime</p>
        <h1>Command Overview</h1>
      </div>
      <div className="topbar-status">
        <div className={`connection-pill status-${wsLabel}`}>
          WS {wsLabel}
        </div>
        <div className="topbar-meta">
          <span>Last alert message</span>
          <strong>{lastMessageAt ? formatDateTime(lastMessageAt) : 'N/A'}</strong>
        </div>
        <div className="topbar-meta">
          <span>Reconnects</span>
          <strong>{reconnectCount ?? 0}</strong>
        </div>
      </div>
    </header>
  )
}
