import { formatNumber } from '../../utils/formatters'

export default function StatusBar({ metrics = {}, health }) {
  return (
    <footer className="statusbar">
      <span>Runtime: <strong>{health?.status || 'unknown'}</strong></span>
      <span>Frames: <strong>{formatNumber(metrics.frames_processed)}</strong></span>
      <span>Dropped: <strong>{formatNumber(metrics.frames_dropped)}</strong></span>
      <span>Alerts: <strong>{formatNumber(metrics.alerts_created)}</strong></span>
      <span>WS Clients: <strong>{formatNumber(metrics.websocket_clients)}</strong></span>
    </footer>
  )
}
