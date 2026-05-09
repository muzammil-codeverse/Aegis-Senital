import { useState } from 'react'
import { normalizeError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login, loading, error } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [localError, setLocalError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setLocalError(null)
    try {
      await login(username, password, { remember })
      window.location.hash = ''
    } catch (err) {
      setLocalError(normalizeError(err))
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={handleSubmit}>
        <div>
          <div className="brand-mark">AS</div>
          <p className="eyebrow">Aegis Sentinel</p>
          <h1>Operator Login</h1>
        </div>
        <label>
          <span>Username</span>
          <input
            value={username}
            onChange={event => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label>
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={remember}
            onChange={event => setRemember(event.target.checked)}
          />
          <span>Keep session on this workstation</span>
        </label>
        {(localError || error) && <div className="form-error">{localError || error}</div>}
        <button className="primary-button" type="submit" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
