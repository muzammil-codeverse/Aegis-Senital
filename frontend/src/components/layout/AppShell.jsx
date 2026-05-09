import Sidebar from './Sidebar'
import TopBar from './TopBar'
import StatusBar from './StatusBar'

export default function AppShell({
  children,
  currentPage,
  onNavigate,
  metrics,
  health,
  websocketStatus,
  lastMessageAt,
  reconnectCount,
}) {
  return (
    <div className="app-shell">
      <Sidebar currentPage={currentPage} onNavigate={onNavigate} />
      <div className="app-frame">
        <TopBar
          websocketStatus={websocketStatus}
          lastMessageAt={lastMessageAt}
          reconnectCount={reconnectCount}
        />
        <main className="app-main">{children}</main>
        <StatusBar metrics={metrics} health={health} />
      </div>
    </div>
  )
}
