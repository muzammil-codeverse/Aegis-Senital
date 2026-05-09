export default function AlertControls({ alert, onAcknowledge, onResolve, onEscalate, busy }) {
  if (!alert) return null
  const alertId = alert.alert_id
  const state = String(alert.state || '').toLowerCase()
  const terminal = ['resolved', 'expired', 'suppressed'].includes(state)

  return (
    <div className="alert-controls">
      <button
        type="button"
        className="control-button"
        disabled={terminal || busy === `acknowledge:${alertId}`}
        onClick={() => onAcknowledge(alertId, 'operator')}
      >
        Acknowledge
      </button>
      <button
        type="button"
        className="control-button"
        disabled={terminal || busy === `resolve:${alertId}`}
        onClick={() => onResolve(alertId, 'operator')}
      >
        Resolve
      </button>
      <button
        type="button"
        className="control-button danger"
        disabled={terminal || busy === `escalate:${alertId}`}
        onClick={() => onEscalate(alertId, 'operator escalation requested')}
      >
        Escalate
      </button>
    </div>
  )
}
