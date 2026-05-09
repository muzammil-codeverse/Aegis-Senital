import { useAuth } from '../../hooks/useAuth'

export default function SessionExpiredBanner() {
  const { sessionExpired, clearSessionNotice } = useAuth()
  if (!sessionExpired) return null
  return (
    <div className="session-banner">
      <span>Your session expired. Sign in again to continue.</span>
      <button type="button" className="text-button" onClick={clearSessionNotice}>Dismiss</button>
    </div>
  )
}
