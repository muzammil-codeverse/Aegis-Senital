import { useState } from 'react'
import { normalizeError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'

export default function ChangePasswordModal({ open, onClose }) {
  const { changePassword } = useAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  if (!open) return null

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      onClose()
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setSaving(false)
    }
  }

  function close() {
    setCurrentPassword('')
    setNewPassword('')
    setError(null)
    onClose()
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal-panel" onSubmit={submit}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Account</p>
            <h2>Change Password</h2>
          </div>
          <button type="button" className="icon-button" onClick={close}>X</button>
        </div>
        <label>
          <span>Current password</span>
          <input
            type="password"
            value={currentPassword}
            onChange={event => setCurrentPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <label>
          <span>New password</span>
          <input
            type="password"
            value={newPassword}
            onChange={event => setNewPassword(event.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="button-row">
          <button type="submit" className="primary-button" disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
          <button type="button" className="text-button" onClick={close}>Cancel</button>
        </div>
      </form>
    </div>
  )
}
