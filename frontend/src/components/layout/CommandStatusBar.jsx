import { formatNumber } from '../../utils/formatters'

export default function CommandStatusBar({ metrics = {}, runtimeStatus, currentPage }) {
  return (
    <footer className="command-statusbar">
      <span>Route <strong>{currentPage}</strong></span>
      <span>Frames <strong>{formatNumber(metrics.frames_processed)}</strong></span>
      <span>Dropped <strong>{formatNumber(metrics.frames_dropped)}</strong></span>
      <span>Alerts <strong>{formatNumber(metrics.alerts_created)}</strong></span>
      <span>WS clients <strong>{formatNumber(metrics.websocket_clients)}</strong></span>
      <span>Overall <strong>{runtimeStatus?.overall || 'unknown'}</strong></span>
    </footer>
  )
}
