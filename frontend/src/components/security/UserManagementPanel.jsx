import { useEffect, useState } from 'react'
import { createUser, disableUser, getRoles, getUsers, lockUser, updateUser } from '../../api/securityApi'
import { normalizeError } from '../../api/client'
import RoleBadge from '../auth/RoleBadge'

const DEFAULT_FORM = {
  username: '',
  password: '',
  display_name: '',
  role: 'viewer',
}

export default function UserManagementPanel() {
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [form, setForm] = useState(DEFAULT_FORM)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function refresh() {
    setLoading(true)
    try {
      const [userResponse, roleResponse] = await Promise.all([getUsers(), getRoles()])
      setUsers(userResponse.items || [])
      setRoles((roleResponse.items || []).map(item => item.role))
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    try {
      await createUser({
        username: form.username,
        password: form.password,
        display_name: form.display_name || null,
        role: form.role,
      })
      setForm(DEFAULT_FORM)
      await refresh()
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function changeRole(user, role) {
    await updateUser(user.user_id, { role })
    await refresh()
  }

  async function runUserAction(action, userId) {
    try {
      if (action === 'disable') await disableUser(userId)
      if (action === 'lock') await lockUser(userId)
      await refresh()
    } catch (err) {
      setError(normalizeError(err))
    }
  }

  return (
    <section className="panel security-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Security</p>
          <h2>User Management</h2>
        </div>
        <button type="button" className="text-button" onClick={refresh}>Refresh</button>
      </div>
      {error && <div className="form-error">{error}</div>}
      <form className="inline-form user-form" onSubmit={submit}>
        <input
          placeholder="Username"
          value={form.username}
          onChange={event => setForm({ ...form, username: event.target.value })}
          required
        />
        <input
          placeholder="Display name"
          value={form.display_name}
          onChange={event => setForm({ ...form, display_name: event.target.value })}
        />
        <input
          type="password"
          placeholder="Temporary password"
          value={form.password}
          onChange={event => setForm({ ...form, password: event.target.value })}
          required
        />
        <select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })}>
          {(roles.length ? roles : ['viewer', 'operator', 'analyst', 'supervisor', 'admin']).map(role => (
            <option key={role} value={role}>{role}</option>
          ))}
        </select>
        <button type="submit" disabled={saving}>{saving ? 'Creating...' : 'Create User'}</button>
      </form>
      {loading ? (
        <div className="muted">Loading users...</div>
      ) : (
        <div className="table-scroll">
          <table className="security-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(user => (
                <tr key={user.user_id}>
                  <td>
                    <strong>{user.display_name || user.username}</strong>
                    <span className="table-subtext">{user.username}</span>
                  </td>
                  <td>
                    <select value={user.role} onChange={event => changeRole(user, event.target.value)}>
                      {(roles.length ? roles : ['viewer', 'operator', 'analyst', 'supervisor', 'admin']).map(role => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </td>
                  <td><RoleBadge role={user.status} /></td>
                  <td>{user.last_login_at ? new Date(user.last_login_at * 1000).toLocaleString() : 'Never'}</td>
                  <td>
                    <div className="button-row">
                      <button type="button" className="text-button" onClick={() => runUserAction('lock', user.user_id)}>Lock</button>
                      <button type="button" className="text-button danger" onClick={() => runUserAction('disable', user.user_id)}>Disable</button>
                    </div>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan="5" className="muted">No users found</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
